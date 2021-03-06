from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import and_
from libs.model import Image
from libs.model import Tag

from libs.model import Base

engine = create_engine('sqlite:///sqlalchemy_example.db')
# Bind the engine to the metadata of the Base class so that the
# declaratives can be accessed through a DBSession instance
Base.metadata.bind = engine

DBSession = sessionmaker(bind=engine)


class ImageDescendants:
  def __init__(self, registry):
    self.registry = registry

  def printDatabase(self):
    """ vylistovani vrstev """
    print "layers listing"
    layers = self.registry.search()['results']
    for layerId in layers:
      images = Image.query.filter_by(layer=layerId).all()
      for img in images:
        print img

    print "layers listed"

    return None


  def longIdFromShort(self, shortId):
    """ returns 64 byte id for given 12 byte id. """
    DBSession = sessionmaker(bind=engine)
    session = DBSession()

    likeString = shortId + "%"
    print likeString
    longIds = [x[0] for x in session.query(Image.id).filter(Image.id.like(likeString)).all()]
    session.close();

    return longIds

  def imageIsIndexed(self, rawId):
    """
    Returns true if image is found in index in database
    """
    DBSession = sessionmaker(bind=engine)
    session = DBSession()
    images = session.query(Image.id).filter(Image.id == rawId).first()
    session.close();
    return not images == None

  def findDescendants(self, rawId):
    """ Find all descending images for image with given id using database"""
    toFind = [rawId]
    result = []

    DBSession = sessionmaker(bind=engine)
    session = DBSession()

    while len(toFind) > 0:

      images = session.query(Image).filter(Image.parent.in_(toFind)).all()

      result.extend(images)
      for image in images:
        image.shortId = image.id[0:12]
        if image.parent != None:
          image.shortParent = image.parent[0:12]

      toFind = [i.id for i in images]

    session.close();
    return result

  def deleteAll(self):
    DBSession = sessionmaker(bind=engine)
    session = DBSession()

    img = session.query(Image).all()
    for x in img:
      print "delete" + str(x)
      session.delete(x)
    session.commit()

  def listAll(self):
    DBSession = sessionmaker(bind=engine)
    session = DBSession()

    img = session.query(Image).all()
    for x in img:
      print x


  def getLayerNames(self):
    """
    Returns name of all layers in registry
    :return:
    """
    allLayers = self.registry.search()
    allLayerNames = set([x['name'] for x in allLayers['results']])
    return allLayerNames

  def listDescendants(self, myTagId):
    descendantGraph = []

    foundDescendants = self.findDescendants(myTagId)

    for descendant in foundDescendants:
      descendantGraph.append({'name': descendant.id[0:12], 'layer': descendant.layer, 'parent': descendant.id[0:12]})

    return {'descendants': foundDescendants, 'graph': descendantGraph}

  def updateTagIndex(self):
    """
    Loads all known tags from repositories and save the unknown ones.
    """
    DBSession = sessionmaker(bind=engine)
    session = DBSession()

    global_old_tag_cnt = 0
    global_new_tag_cnt = 0
    global_changed_tag_cnt = 0
    global_errors_cnt = 0
    lines = []

    # List all tags in all layers:
    for layerName in self.getLayerNames():
      print "scanning layer " + str(layerName)
      local_old_tag_cnt = 0
      local_new_tag_cnt = 0
      local_changed_tag_cnt = 0;
      local_errors_cnt = 0

      try:
        tags = self.registry.get_tags(layerName)

        for tagName, imageId in tags.iteritems():

          query_filter = and_(Tag.layer == layerName, Tag.tag == tagName)
          ids_in_database = [x[0] for x in session.query(Tag.id).filter(query_filter).all()];

          tag_is_new = ids_in_database is None or len(ids_in_database) == 0
          tag_changed = False;
          if not tag_is_new:
            tag_changed = not (imageId in ids_in_database)

          if tag_is_new or tag_changed:
            session2 = DBSession()
            session2.add(Tag(id=imageId, layer=layerName, tag=tagName))
            session2.commit();
            session2.close();

            if tag_is_new:
              lines.append("New tag: " + layerName + " " + tagName);
              global_new_tag_cnt += 1
              local_new_tag_cnt += 1

            if tag_changed:
              lines.append("Tag target changed: " + layerName + " " + tagName + " to " + str(imageId));
              global_changed_tag_cnt += 1
              local_changed_tag_cnt += 1

          else:
            global_old_tag_cnt += 1
            local_old_tag_cnt += 1

      except Exception as e:
        global_errors_cnt += 1
        local_errors_cnt += 1
        lines.append("Cannot process layer " + str(layerName) + ": " + str(e));
        raise e

      lines.append("Layer " + str(layerName) + " scanned - found " + str(local_changed_tag_cnt) +
                   " changed and " + str(local_new_tag_cnt) + " new tags with " +
                   str(local_errors_cnt) + " errors");

    session.close();
    msg = "Tag index update finished: \"" + str(global_new_tag_cnt) + "\" changed tags found."
    lines.append(msg);
    print msg
    return {'newImages': global_new_tag_cnt, 'oldImages': global_old_tag_cnt, 'results': lines,
            'errors': global_errors_cnt}


  def updateDescendantIndex(self):
    DBSession = sessionmaker(bind=engine)
    session = DBSession()

    alreadySavedImageIds = [x[0] for x in session.query(Image.id).all()]

    new_imageCount = 0
    old_imagesCount = 0
    totalNewImages = 0
    lines = []
    errorfound = False

    for layerName in self.getLayerNames():
      try:
        print layerName
        allNewImages = set([x['id'] for x in self.registry.get_images(layerName)])
        DBSession = sessionmaker(bind=engine)
        errorsCount = 0

        for newImageId in allNewImages:

          if (new_imageCount + old_imagesCount) % 20 == 0:
            print "status: " + str(new_imageCount) + " new images, " \
                  + str(old_imagesCount) + " old images addded with " + str(errorsCount) + " errors"

          if newImageId in alreadySavedImageIds:
            old_imagesCount += 1
          else:
            new_imageCount += 1

            new_image = Image(id=newImageId, layer=layerName)

            try:
              extendedinfo = self.registry.get_image_info(newImageId)

              if 'author' in extendedinfo:
                new_image.author = extendedinfo['author']

              if 'parent' in extendedinfo:
                new_image.parent = extendedinfo['parent']
            except Exception as e:
              msg = "Cannot load extended info for image " + newImageId + " " + str(e)
              errorsCount += 1
              errorfound = True
              lines.append(msg)

            totalNewImages += 1

            try:
              session = DBSession()
              session.add(new_image)
              session.commit()
              alreadySavedImageIds.append(newImageId)
            except Exception as e:
              print "Already exists:" + str(newImageId) + " " + str(newImageId in alreadySavedImageIds) + "\n\n"
              raise e

        if not errorfound:
          lines.append("Layer " + layerName + " processed without errors")
        else:
          lines.append("Layer " + layerName + " processed with errors")

        print "  Old images=" + str(old_imagesCount) + " new images=" + str(new_imageCount)
      except Exception as e:
        msg = "I cant process layer " + layerName + " " + str(e)
        lines.append(msg)
        print msg

    print "Total new images:" + str(totalNewImages)
    return {'newImages': new_imageCount, 'oldImages': old_imagesCount, 'results': lines, 'errors': errorsCount}