"""
Link edge points in an image to lists.
Convert from matlab code, author is Peter Kovesi
Please see https://www.peterkovesi.com/matlabfns/

Copyright (c) 2018- Guoxia Wang
mingzilaochongtu at gmail com

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal 
in the Software without restriction, subject to the following conditions:

The above copyright notice and this permission notice shall be included in 
all copies or substantial portions of the Software.

The Software is provided "as is", without warranty of any kind.
"""

import numpy as np
import scipy.ndimage
import bwmorph

def edgelink(im):
    """
    EDGELINK - Link edge points in an image into lists
    Arguments:  im         - Binary edge image, it is assumed that edges
                             have been thinned (or are nearly thin).

    Returns:  edgelist - a edge lists in row, column coords

              edgeim   - Image with pixels labeled with edge number. 
                         Note that junctions in the labeled edge image will be
                         labeled with the edge number of the last edge that was
                         tracked through it.  Note that this image also includes
                         edges that do not meet the minimum length specification.
                         If you want to see just the edges that meet the
                         specification you should pass the edgelist to
                         DRAWEDGELIST.

               etype   - Array of values, one for each edge segment indicating
                         its type
                         0  - Start free, end free
                         1  - Start free, end junction
                         2  - Start junction, end free (should not happen)
                         3  - Start junction, end junction
                         4  - Loop


    This function links edge points together into lists of coordinate pairs.
    Where an edge junction is encountered the list is terminated and a separate
    list is generated for each of the branches.
    """
    
    # Make sure image is binary.
    edgeim = (im != 0).astype(np.int8)

    # Fill one pixel hole 
    edgeim = scipy.ndimage.binary_closing(edgeim, structure=np.ones((2, 2))).astype(np.int8)
    # Make sure edges are thinned.
    edgeim = bwmorph.thin(edgeim).astype(np.int8)
    rows, cols = edgeim.shape

    # Find endings and junctions in edge data
    # RJ, CJ, re, ce = findEndsJunctions(edgeim)
    # We use bwmorph.branches and endpoints to avoid too long time 
    # so that it can lead to freeze pyqt GUI main thread
    RJ, CJ = np.where(bwmorph.branches(edgeim))
    re, ce = np.where(bwmorph.endpoints(edgeim))

    # Create a dictionary to mark junction locations. This makes junction
    # testing much faster.  A value of 1 indicates a junction, a value of 2
    # indicates we have visited the junction.
    junct = {}
    for n in range(len(RJ)):
        junct[(RJ[n], CJ[n])] = 1

    edgeNo = 0
    edgelist = []
    etype = []
    # Summary of strategy:
    # 1) From every end point track until we encounter an end point or
    # junction.  As we track points along an edge image pixels are labeled with
    # the -ve of their edge No.
    # 2) From every junction track out on any edges that have not been
    # labeled yet.
    # 3) Scan through the image looking for any unlabeled pixels.  These
    # correspond to isolated loops that have no junctions.
    
    # 1) Form tracks from each unlabeled endpoint until we encounter another
    # endpoint or junction.
    for n in range(len(re)):
        if (edgeim[re[n], ce[n]] == 1): # Endpoint is unlabeled
            edgeNo += 1
            edgepoints, endType = trackEdge(edgeim, junct, re[n], ce[n], edgeNo)
            edgelist.append(edgepoints)
            etype.append(endType)

    # 2) Handle junctions.
    # Junctions are awkward when they are adjacent to other junctions.  We
    # start by looking at all the neighbours of a junction.  
    # If there is an adjacent junction we first create a 2-element edgetrack
    # that links the two junctions together.  We then look to see if there are
    # any non-junction edge pixels that are adjacent to both junctions. We then
    # test to see which of the two junctions is closest to this common pixel and
    # initiate an edge track from the closest of the two junctions through this
    # pixel.  When we do this we set the 'avoidJunction' flag in the call to
    # trackedge so that the edge track does not immediately loop back and
    # terminate on the other adjacent junction.
    # Having checked all the common neighbours of both junctions we then
    # track out on any remaining untracked neighbours of the junction 

    for j in range(len(RJ)):
        # We have not visited this junction
        if (junct[(RJ[j], CJ[j])] != 2): 
            junct[(RJ[j], CJ[j])] = 2

            # Call availablepixels with edgeNo = 0 so that we get a list of
            # available neighbouring pixels that can be linked to and a list of
            # all neighbouring pixels that are also junctions.
            ra, ca, rj, cj = availablePixels(edgeim, junct, RJ[j], CJ[j], 0)

            # For all adjacent junctions...
            for k in range(len(rj)):
                # Create a 2-element edgetrack to each adjacent junction
                edgeNo += 1
                edgelist.append([[RJ[j], CJ[j]], [rj[k], cj[k]]])
                etype.append(3) # Edge segment is junction-junction
                edgeim[RJ[j], CJ[j]] = -edgeNo
                edgeim[rj[k], cj[k]] = -edgeNo

                # Check if the adjacent junction has some untracked pixels that
                # are also adjacent to the initial junction.  Thus we need to
                # get available pixels adjacent to junction (rj(k) cj(k))
                rak, cak, rjk, cjk = availablePixels(edgeim, junct, rj[k], cj[k])

                # If both junctions have untracked neighbours that need checking...
                if (len(ra) > 0 and len(rak) > 0):
                    # Find untracked neighbours common to both junctions. 
                    raca = np.array([[ra[i], ca[i]] for i in range(len(ra))])
                    rakcak = np.array([[rak[i], cak[i]] for i in range(len(rak))])
                    commonrc = intersect(raca, rakcak)

                    for n in range(commonrc.shape[0]):
                        # If one of the junctions j or k is closer to this common
                        # neighbour use that as the start of the edge track and the
                        # common neighbour as the 2nd element. When we call
                        # trackedge we set the avoidJunction flag to prevent the
                        # track immediately connecting back to the other junction.
                        distj = norm(commonrc[n] - np.array([RJ[j], CJ[j]]))
                        distk = norm(commonrc[n] - np.array([rj[k], cj[k]]))
                        edgeNo += 1
                        if (distj < distk):
                            edgepoints, endType = trackEdge(edgeim, junct, 
                                RJ[j], CJ[j], edgeNo, commonrc[n][0], commonrc[n][1], 1)
                            edgelist.append(edgepoints)
                        else:
                            edgepoints, endType = trackEdge(edgeim, junct,
                                rj[k], cj[k], edgeNo, commonrc[n][0], commonrc[n][1], 1)
                            edgelist.append(edgepoints)
                        etype.append(3) # Edge segment is junction-junction

                # Track any remaining unlabeled pixels adjacent to this junction k
                for m in range(len(rak)):
                    if (edgeim[rak[m], cak[m]] == 1):
                        edgeNo += 1
                        edgepoints, endType = trackEdge(edgeim, junct,
                            rj[k], cj[k], edgeNo, rak[m], cak[m])
                        edgelist.append(edgepoints)
                        etype.append(3) # Edge segment is junction-junction

                # Mark that we have visited junction (rj(k) cj(k))
                junct[(rj[k], cj[k])] = 2

            # Finally track any remaining unlabeled pixels adjacent to original junction j
            for m in range(len(ra)):
                if (edgeim[ra[m], ca[m]] == 1):
                    edgeNo += 1
                    edgepoints, endType = trackEdge(edgeim, junct,
                        RJ[j], CJ[j], edgeNo, ra[m], ca[m])
                    edgelist.append(edgepoints)
                    etype.append(3) # Edge segment is junction-junction

    # 3) Scan through the image looking for any unlabeled pixels.  These
    # should correspond to isolated loops that have no junctions or endpoints.
    ru, cu = np.where(edgeim == 1)
    for j in range(len(ru)):
        edgeNo += 1
        edgepoints, endType = trackEdge(edgeim, junct, ru[j], cu[j], edgeNo)
        edgelist.append(edgepoints)
        etype.append(endType)

    # Finally negate image to make edge encodings +ve.
    edgeim = -edgeim

    return (edgelist, edgeim, etype)

def findEndsJunctions(edgeim):
    """
    FINDENDSJUNCTIONS - find junctions and endings in a line/edge image
    Arguments:  edgeim - A binary image marking lines/edges in an image.  It is
                         assumed that this is a thinned or skeleton image 
    Returns:    rj, cj - Row and column coordinates of junction points in the
                         image. 
                re, ce - Row and column coordinates of end points in the
                         image.
    """
    def junction(x):
        """
        Function to test whether the centre pixel within a 3x3 neighbourhood is a
        junction. The centre pixel must be set and the number of transitions/crossings
        between 0 and 1 as one traverses the perimeter of the 3x3 region must be 6 or
        8.

        Pixels in the 3x3 region are numbered as follows

              0 1 2
              3 4 5
              6 7 8    
        """
        a = np.array([x[0], x[1], x[2], x[5], x[8], x[7], x[6], x[3]], dtype=np.int8)
        b = np.array([x[1], x[2], x[5], x[8], x[7], x[6], x[3], x[0]], dtype=np.int8)
        crossings = np.sum(np.abs(a - b))
        return (x[4] and crossings >= 6)

    def ending(x):
        """
        Function to test whether the centre pixel within a 3x3 neighbourhood is an
        ending. The centre pixel must be set and the number of transitions/crossings
        between 0 and 1 as one traverses the perimeter of the 3x3 region must be 2.

        Pixels in the 3x3 region are numbered as follows

              0 1 2
              3 4 5
              6 7 8
        """
        a = np.array([x[0], x[1], x[2], x[5], x[8], x[7], x[6], x[3]], dtype=np.int8)
        b = np.array([x[1], x[2], x[5], x[8], x[7], x[6], x[3], x[0]], dtype=np.int8)
        crossings = np.sum(np.abs(a - b))
        return (x[4] and crossings == 2)

    junctions = scipy.ndimage.generic_filter(edgeim, junction, size=(3, 3))
    rj, cj = np.where(junctions)

    ends = scipy.ndimage.generic_filter(edgeim, ending, size=(3, 3))
    re, ce = np.where(ends)

    return (rj, cj, re, ce)


def trackEdge(edgeim, junct, rstart, cstart, edgeNo, r2=None, c2=None, avoidJunction=0):
    """
    TRACKEDGE
    
    Function to track all the edge points starting from an end point or junction.
    As it tracks it stores the coords of the edge points in an array and labels the
    pixels in the edge image with the -ve of their edge number. This continues
    until no more connected points are found, or a junction point is encountered.
    
    Usage:   edgepoints = trackEdge(img, junct, rstart, cstart, edgeNo, r2, c2, avoidJunction)
    
    Arguments:   edgeim           - MxN numpy array, binary edge image
                 junct            - A dictionary (where key is tuple (r, c)) to
                                    mark junction locations
                 rstart, cstart   - Row and column No of starting point.
                 edgeNo           - The current edge number.
                 r2, c2           - Optional row and column coords of 2nd point.
                 avoidJunction    - Optional flag indicating that (r2,c2)
                                    should not be immediately connected to a
                                    junction (if possible).
    
    Returns:     edgepoints       - Nx2 array of row and col values for
                                    each edge point.
                 endType          - 0 for a free end
                                    1 for a junction
                                    5 for a loop
    """
    # Start a new list for this edge.
    edgepoints = [[rstart, cstart]] 

    # Edge points in the image are encoded by -ve of their edgeNo.
    edgeim[rstart, cstart] = -edgeNo 

    # Flag indicating we have/not a preferred direction.
    preferredDirection = 0

    # Initialise direction vector of path and set the current point on the path
    dirn = [0, 0]
    r = rstart
    c = cstart

    # If the second point has been supplied add it to the track and set the path direction
    if (r2 is not None and c2 is not None):
        edgepoints.append([r2, c2])
        edgeim[r2, c2] = -edgeNo
        dirn = unitVector([r2-rstart, c2-cstart])
        r = r2
        c = c2
        preferredDirection = 1

    # Find all the pixels we could link to
    ra, ca, rj, cj = availablePixels(edgeim, junct, r, c, edgeNo)
    while (len(ra) > 0 or len(rj) > 0):
        # First see if we can link to a junction. Choose the junction that
        # results in a move that is as close as possible to dirn. If we have no
        # preferred direction, and there is a choice, link to the closest
        # junction
        # We enter this block:
        # IF there are junction points and we are not trying to avoid a junction
        # OR there are junction points and no non-junction points, ie we have
        # to enter it even if we are trying to avoid a junction
        dirnbest = [0, 0]
        rbest = -1
        cbest = -1
        if (len(rj) > 0 and (not avoidJunction or len(ra) == 0)):
            # If we have a prefered direction choose the junction that results
            # in a move that is as close as possible to dirn.
            if (preferredDirection):
                dotp = -np.inf
                for n in range(len(rj)):
                    dirna = unitVector([rj[n]-r, cj[n]-c])
                    dp = np.dot(np.ravel(dirn), np.ravel(dirna).T)
                    if (dp > dotp):
                        dotp = dp
                        rbest = rj[n]
                        cbest = cj[n]
                        dirnbest = dirna
            # Otherwise if we have no established direction, we should pick a
            # 4-connected junction if possible as it will be closest.  This only
            # affects tracks of length 1 (Why do I worry about this...?!).
            else:
                distbest = np.inf
                for n in range(len(rj)):
                    dist = np.sum(np.abs([rj[n]-r, cj[n]-c]))
                    if (dist < distbest):
                        rbest = rj[n]
                        cbest = cj[n]
                        distbest = dist
                        dirnbest = unitVector([rj[n]-r, cj[n]-c])
                preferredDirection = 1

        # If there were no junctions to link to choose the available
        # non-junction pixel that results in a move that is as close as possible
        # to dirn
        else:
            dotp = -np.inf
            for n in range(len(ra)):
                dirna = unitVector([ra[n]-r, ca[n]-c])
                dp = np.dot(np.ravel(dirn), np.ravel(dirna).T)
                if (dp > dotp):
                    dotp = dp
                    rbest = ra[n]
                    cbest = ca[n]
                    dirnbest = dirna
            # Clear the avoidJunction flag if it had been set
            avoidJunction = 0

        # Append the best pixel to the edgelist and update the direction and EDGEIM
        r = rbest
        c = cbest
        edgepoints.append([r, c])
        dirn = dirnbest
        edgeim[r, c] = -edgeNo

        # If this point is a junction exit here
        if ((r, c) in junct):
            # Mark end as being a junction
            endType = 1
            return (edgepoints, endType)
        else:
            # Get the next set of available pixels to link.
            ra, ca, rj, cj = availablePixels(edgeim, junct, r, c, edgeNo)

    #If we get here we are at an endpoint or our sequence of pixels form a
    #loop.  If it is a loop the edgelist should have start and end points
    #matched to form a loop.  If the number of points in the list is four or
    #more (the minimum number that could form a loop), and the endpoints are
    #within a pixel of each other, append a copy of the first point to the end
    #to complete the loop

    # Mark end as being free, unless it is reset below
    endType = 0
    if (len(edgepoints) >= 4):
        if (np.abs(edgepoints[0][0] - edgepoints[-1][0]) <= 1
            and np.abs(edgepoints[0][1] - edgepoints[-1][1] <= 1)):
            edgepoints.append(edgepoints[0])
            # Mark end as being a loop
            endType = 4
    return (edgepoints, endType)
        

def availablePixels(edgeim, junct, rp, cp, edgeNo=0):
    """
     AVAILABLEPIXELS

     Find all the pixels that could be linked to point r, c

     Arguments:  edgeim - MxN numpy array, binary edge image
                 junct  - A dictionary (where key is tuple (r, c)) to
                          mark junction locations
                 rp, cp - Row, col coordinates of pixel of interest.
                 edgeNo - The edge number of the edge we are seeking to
                          track. If not supplied its value defaults to 0
                          resulting in all adjacent junctions being returned,
                          (see note below)

     Returns:    ra, ca - Row and column coordinates of available non-junction
                          pixels.
                 rj, cj - Row and column coordinates of available junction
                          pixels.

     A pixel is avalable for linking if it is:
     1) Adjacent, that is it is 8-connected.
     2) Its value is 1 indicating it has not already been assigned to an edge
     3) or it is a junction that has not been labeled -edgeNo indicating we have
        not already assigned it to the current edge being tracked.  If edgeNo is
        0 all adjacent junctions will be returned
    """
    ra = []
    ca = []
    rj = []
    cj = []

    # row and column offsets for the eight neighbours of a point
    roff = np.array([-1,  0,  1, 1, 1, 0, -1, -1])
    coff = np.array([-1, -1, -1, 0, 1, 1,  1,  0])

    r = rp + roff
    c = cp + coff

    rows, cols = edgeim.shape
    # Find indices of arrays of r and c that are within the image bounds
    ind = np.where(np.logical_and(np.logical_and(r>=0, r<rows), np.logical_and(c>=0, c<cols)))[0]

    # A pixel is avalable for linking if its value is 1 or it is a junction
    # that has not been labeled -edgeNo
    for i in ind:
        if (edgeim[r[i], c[i]] == 1 and (not (r[i], c[i]) in junct)):
            ra.append(r[i])
            ca.append(c[i])
        elif (edgeim[r[i], c[i]] != -edgeNo and (r[i], c[i]) in junct):
            rj.append(r[i])
            cj.append(c[i])

    return (ra, ca, rj, cj)
    
def norm(v):
    return np.sqrt(np.dot(np.ravel(v).T, np.ravel(v)))

def unitVector(v):
    return (v / np.sqrt(np.dot(np.ravel(v).T, np.ravel(v))))

def intersect(A, B):
    return np.array([x for x in set(tuple(x) for x in A) & set(tuple(x) for x in B)])
