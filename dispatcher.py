import math
import numpy
import heapq

# a data container for all pertinent information related to fares. (Should we
# add an underway flag and require taxis to acknowledge collection to the dispatcher?)
class FareEntry:

      def __init__(self, origin, dest, time, price=0, taxiIndex=-1):

          self.origin = origin
          self.destination = dest
          self.calltime = time
          self.price = price
          # the taxi allocated to service this fare. -1 if none has been allocated
          self.taxi = taxiIndex
          # a list of indices of taxis that have bid on the fare.
          self.bidders = []

'''
A Dispatcher is a static agent whose job is to allocate fares amongst available taxis. Like the taxis, all
the relevant functionality happens in ClockTick. The Dispatcher has a list of taxis, a map of the service area,
and a dictionary of active fares (ones which have called for a ride) that it can use to manage the allocations.
Taxis bid after receiving the price, which should be decided by the Dispatcher, and once a 'satisfactory' number
of bids are in, the dispatcher should run allocateFare in its world (parent) to inform the winning bidder that they
now have the fare.
'''
class Dispatcher:

      # constructor only needs to know the world it lives in, although you can also populate its knowledge base
      # with taxi and map information.
      def __init__(self, parent, taxis=None, serviceMap=None):

          self._parent = parent
          # our incoming account
          self._revenue = 0
          # the list of taxis
          self._taxis = taxis
          if self._taxis is None:
             self._taxis = []
          # fareBoard will be a nested dictionary indexed by origin, then destination, then call time.
          # Its values are FareEntries. The nesting structure provides for reasonably fast lookup; it's
          # more or less a multi-level hash.
          self._fareBoard = {}
          # serviceMap gives the dispatcher its service area
          self._map = serviceMap

      #_________________________________________________________________________________________________________
      # methods to add objects to the Dispatcher's knowledge base
      
      # make a new taxi known.
      def addTaxi(self, taxi):
          if taxi not in self._taxis:
             self._taxis.append(taxi)

      # added 26 August 2026
      # remove an existing taxi
      # FIXME deal with cases where the taxi has allocations
      def removeTaxi(self, taxi):
          try:
              del self._taxis[self._taxis.index(taxi)]
          except ValueError:
              pass

      # incrementally add to the map. This can be useful if, e.g. the world itself has a set of
      # nodes incrementally added. It can then call this function on the dispatcher to add to
      # its map
      def addMapNode(self, coords, neighbours):
          if self._parent is None:
             return AttributeError("This Dispatcher does not exist in any world")
          node = self._parent.getNode(coords[0],coords[1])
          if node is None:
             return KeyError("No such node: {0} in this Dispatcher's service area".format(coords))
          # build up the neighbour dictionary incrementally so we can check for invalid nodes.
          neighbourDict = {}
          for neighbour in neighbours:
              neighbourCoords = (neighbour[1], neighbour[2])
              neighbourNode = self._parent.getNode(neighbour[1],neighbour[2])
              if neighbourNode is None:
                 return KeyError("Node {0} expects neighbour {1} which is not in this Dispatcher's service area".format(coords, neighbour))
              neighbourDict[neighbourCoords] = (neighbour[0],self._parent.distance2Node(node, neighbourNode))
          self._map[coords] = neighbourDict

      # importMap gets the service area map, and can be brought in incrementally as well as
      # in one wodge.
      def importMap(self, newMap):
          # a fresh map can just be inserted
          if self._map is None:
             self._map = newMap
          # but importing a new map where one exists implies adding to the
          # existing one. (Check that this puts in the right values!)
          else:
             for node in newMap.items():
                 neighbours = [(neighbour[1][0],neighbour[0][0],neighbour[0][1]) for neighbour in node[1].items()]
                 self.addMapNode(node[0],neighbours)

      # handover pushes the Dispatcher's known information to a new one coming on. It dumps the complete fare board to the
      # new dispatcher.
      def handover(self, newDispatcher):
          world = self._parent # sending the world makes sure we are operating in the same environment
          # DEBUGME we hope this is the right way of expanding a comprehension to unroll a dictionary
          compressedFareBoard = ((o[0], d[0], t[0], t[1]) for t in k for k in d[1].items() for d in j for j in o[1].items() for o in i for i in self.fareboard.items())
          for f in compressedFareBoard:
              if not newDispatcher.receiveHandover(self._parent, f[0], f[1], f[2], f[3].taxi, f[3].price):
                 return False # handover failed if the new Dispatcher didn't know the parent world
          return True 

      # any legacy fares or taxis from a previous dispatcher can be imported here - future functionality,
      # for the most part
      # FIXME integrate with handover above
      def receiveHandover(self, parent, origin, destination, time, taxi=None, price=0):
          if self._parent == parent:
             # handover implies taxis definitely known to a previous dispatcher. The current
             # dispatcher should thus be made aware of them
             if taxi not in self._taxis:
                self._taxis.append(taxi)
             # add any fares found along with their allocations
             self.newFare(parent, origin, destination, time)
             self._fareBoard[origin][destination][time].taxi = self._taxis.index(taxi)
             self._fareBoard[origin][destination][time].price = price
             return True # successful handover
          return False # unknown networld. Fail.

      #--------------------------------------------------------------------------------------------------------------
      # runtime methods used to inform the Dispatcher of real-time events


      # fares will call this when they appear to signal a request for service.
      def newFare(self, parent, origin, destination, time):
          # only add new fares coming from the same world
          if parent == self._parent:
             fare = FareEntry(origin,destination,time)
             if origin in self._fareBoard:               
                if destination not in self._fareBoard[origin]:
                   self._fareBoard[origin][destination] = {}
             else:
                self._fareBoard[origin] = {destination: {}}
             # overwrites any existing fare with the same (origin, destination, calltime) triplet, but
             # this would be equivalent to saying it was the same fare, at least in this world where
             # a given Node only has one fare at a time.
             self._fareBoard[origin][destination][time] = fare
             
      # abandoning fares will call this to cancel their request
      def cancelFare(self, parent, origin, destination, calltime):
          # if the fare exists in our world,
          if parent == self._parent and origin in self._fareBoard:
             if destination in self._fareBoard[origin]:
                if calltime in self._fareBoard[origin][destination]:
                   # get rid of it
                   print("Fare ({0},{1}) cancelled".format(origin[0],origin[1]))
                   # inform taxis that the fare abandoned
                   self._parent.cancelFare(origin, self._taxis[self._fareBoard[origin][destination][calltime].taxi])
                   del self._fareBoard[origin][destination][calltime]
                if len(self._fareBoard[origin][destination]) == 0:
                   del self._fareBoard[origin][destination]
                if len(self._fareBoard[origin]) == 0:
                   del self._fareBoard[origin]

      # taxis register their bids for a fare using this mechanism
      def fareBid(self, origin, taxi):
          # rogue taxis (not known to the dispatcher) can't bid on fares
          if taxi in self._taxis:
             # everyone else bids on fares available
             if origin in self._fareBoard:
                for destination in self._fareBoard[origin].keys():
                    for time in self._fareBoard[origin][destination].keys():
                        # as long as they haven't already been allocated
                        if self._fareBoard[origin][destination][time].taxi == -1:
                           self._fareBoard[origin][destination][time].bidders.append(self._taxis.index(taxi))
                           # only one fare per origin can be actively open for bid, so
                           # immediately return once we[ve found it
                           return
                     
      # fares call this (through the parent world) when they have reached their destination
      def recvPayment(self, parent, amount):
          # don't take payments from dodgy alternative universes
          if self._parent == parent:
             self._revenue += amount

      #________________________________________________________________________________________________________________

      # clockTick is called by the world and drives the simulation for the Dispatcher. It must, at minimum, handle the
      # 2 main functions the dispatcher needs to run in the world: broadcastFare(origin, destination, price) and
      # allocateFare(origin, taxi).
      def clockTick(self, parent):
          if self._parent == parent:
             for origin in self._fareBoard.keys():
                 for destination in self._fareBoard[origin].keys():
                     # TODO - if you can come up with something better. Not essential though.
                     # not super-efficient here: need times in order, dictionary view objects are not
                     # sortable because they are an iterator, so we need to turn the times into a
                     # sorted list. Hopefully fareBoard will never be too big
                     for time in sorted(list(self._fareBoard[origin][destination].keys())):
                         if self._fareBoard[origin][destination][time].price == 0:
                            self._fareBoard[origin][destination][time].price = self._costFare(self._fareBoard[origin][destination][time])
                            # broadcastFare actually returns the number of taxis that got the info, if you
                            # wish to use that information in the decision over when to allocate
                            self._parent.broadcastFare(origin,
                                                       destination,
                                                       self._fareBoard[origin][destination][time].price)
                         elif self._fareBoard[origin][destination][time].taxi < 0 and len(self._fareBoard[origin][destination][time].bidders) > 0:
                              self._allocateFare(origin, destination, time)

      #----------------------------------------------------------------------------------------------------------------

      ''' HERE IS THE PART THAT YOU NEED TO MODIFY
      '''

      '''this internal method should decide a 'reasonable' cost for the fare. Here, the computation
         is trivial: add a fixed cost (representing a presumed travel time to the fare by a given
         taxi) then multiply the expected travel time by the profit-sharing ratio. Better methods
         should improve the expected number of bids and expected profits. The function gets all the
         fare information, even though currently it's not using all of it, because you may wish to
         take into account other details.
      '''
      # TODO - improve costing
      def _costFare(self, fare):
          timeToDestination = self._parent.travelTime(self._parent.getNode(fare.origin[0],fare.origin[1]),
                                                      self._parent.getNode(fare.destination[0],fare.destination[1]))
          # if the world is gridlocked, a flat fare applies.
          if timeToDestination < 0:
             return 150
          return (25+timeToDestination)/0.9

      # TODO (DONE)
      def _allocateFare(self, origin, destination, time):
          fareNode = self._parent.getNode(origin[0], origin[1])
          if fareNode is None:
             return

          fareEntry = self._fareBoard[origin][destination][time]

          # get valid on-duty bidders
          bidders = []
          for idx in fareEntry.bidders:
              if idx >= 0 and idx < len(self._taxis) and idx not in bidders:
                 if self._taxis[idx].onDuty:
                    bidders.append(idx)

          if len(bidders) == 0:
             return

          # keep count of fares per taxi
          if not hasattr(self, 'fareCounts'):
             self.fareCounts = {}
          for t in self._taxis:
             if t.number not in self.fareCounts:
                self.fareCounts[t.number] = 0

          # check active and idle taxis
          active = []
          idle = 0
          for t in self._taxis:
              if t.onDuty:
                 active.append(t)
                 if t._passenger is None and len(t._path) == 0:
                    idle += 1

          waited = self._parent.simTime - time

          # wait 1 tick if at least 2 idle taxis are free so closer ones can bid
          if len(bidders) < len(active) and waited < 3:
             if idle >= 2 and (waited < 1 or len(bidders) < 2):
                return

          totFares = 0
          totCash = 0
          for t in active:
              totFares += self.fareCounts[t.number]
              totCash += t._account

          n = len(active) if len(active) > 0 else 1
          avgFares = totFares / n
          avgCash = totCash / n

          destNode = self._parent.getNode(destination[0], destination[1])
          if destNode is not None:
             tripDist = self._parent.distance2Node(fareNode, destNode)
          else:
             tripDist = 0

          allocatedTaxi = -1
          bestScore = -100000

          for idx in bidders:
              t = self._taxis[idx]
              bNode = self._parent.getNode(t.currentLocation[0], t.currentLocation[1])
              if bNode is None:
                 continue

              dist = self._parent.distance2Node(bNode, fareNode)

              # don't send a taxi that will run out of cash on the way
              if t._account <= dist + 3:
                 continue

              rem = len(t._path)
              if t._passenger is not None:
                 busy = rem
              else:
                 busy = 0.25 * rem

              profit = fareEntry.price - (dist + busy + tripDist)
              fDiff = avgFares - self.fareCounts[t.number]
              cDiff = avgCash - t._account

              score = (-1.5 * dist) - (0.8 * busy) + (0.25 * profit) + (3.5 * fDiff) + (0.04 * cDiff)

              if score > bestScore:
                 bestScore = score
                 allocatedTaxi = idx

          # fallback to closest if everyone failed the cash check
          if allocatedTaxi < 0:
             minDist = 100000
             for idx in bidders:
                 loc = self._taxis[idx].currentLocation
                 node = self._parent.getNode(loc[0], loc[1])
                 if node is not None:
                    d = self._parent.distance2Node(node, fareNode)
                    if d < minDist:
                       minDist = d
                       allocatedTaxi = idx

          if allocatedTaxi >= 0:
             fareEntry.taxi = allocatedTaxi
             self.fareCounts[self._taxis[allocatedTaxi].number] += 1
             self._parent.allocateFare(origin, self._taxis[allocatedTaxi])


