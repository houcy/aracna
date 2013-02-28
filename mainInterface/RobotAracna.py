import os
from datetime import datetime
from time import sleep
from types import FunctionType
from copy import copy
from numpy import array

import dynamixel #TODO: get rid of this?
from Motion import lInterp, scaleTime

'''
Much inspiration taken from http://code.google.com/p/pydynamixel/
'''



'''Min and max values for the QuadraTot robot, based on some tests.

Note that these values will avoid collisions only for each servo
individually.  More complex collisions are still possible given
certain vectors of motor position.
'''

from ConstantsAracna import *


class RobotFailure(Exception):
    pass



class RobotAracna():
    ''''''

    def __init__(self, expectedIds = None, commandRate = 40, loud = False):
        '''Initialize the robot.
        
        Keyword arguments:

        silentNetworkFail -- Whether or not to fail silently if the
                             network does not find all the dynamixel
                             servos.

        nServos -- How many servos are connected to the robot,
                   i.e. how many to expect to find on the network.

        commandRate -- Rate at which the motors should be commanded,
                   in Hertz.  Default: 40.
                   FIXME: the real command rate is more like 14
        '''

        # The number of Dynamixels on the bus.
        self.expectedIds   = expectedIds if expectedIds is not None else range(8)
        self.nServos       = len(self.expectedIds)

        self.sleep = 1. / float(commandRate)
        self.loud  = loud
            
        self.ser = serial.Serial(port, 38400)
        
        #For debugging purposes only
        self.failedPackets = 0
        self.successfulPackets = 0
        self.startTime = time.clock()
        
    def run(self, motionFunction, runSeconds = 10, resetFirst = True,
            interpBegin = 0, interpEnd = 0, timeScale = 1, logFile = None,
            extraLogInfoFn = None):
        '''Run the robot with a given motion generating function.

        Positional arguments:
        
        motionFunction -- Function used to generate the desired motor
                          positions.  This function must take a single
                          argument -- time, in seconds -- and must
                          return the desired length 9 vector of motor
                          positions.  The current implementation
                          expects that this function will be
                          deterministic.
        
        Keyword arguments:

        runSeconds -- How many seconds to run for.  This is in
                      addition to the time added for interpBegin and
                      interpEnd, if any.  Default: 10

        resetFirst -- Begin each run by resetting the robot to its
                      base position, currently implemented as a
                      transition from CURRENT -> POS_FLAT ->
                      POS_READY.  Default: True

        interpBegin -- Number of seconds over which to interpolate
                      from current position to commanded positions.
                      If this is not None, the robot will spend the
                      first interpBegin seconds interpolating from its
                      current position to that specified by
                      motionFunction.  This should probably be used
                      for motion models which do not return POS_READY
                      at time 0.  Affected by timeScale. Default: None

        interpEnd -- Same as interpBegin, but at the end of motion.
                      If interpEnd is not None, interpolation is
                      performed from final commanded position to
                      POS_READY, over the given number of
                      seconds. Affected by timeScale.  Default: None
                      
        timeScale -- Factor by which time should be scaled during this
                      run, higher is slower. Default: 1
                      
        logFile -- File to log time/positions to, should already be
                      opened. Default: None

        extraLogInfoFn -- Function to call and append info to every
                      line the log file. Should return a
                      string. Default: None
        '''

        #net, actuators = initialize()

        #def run(self, motionFunction, runSeconds = 10, resetFirst = True
        #    interpBegin = 0, interpEnd = 0):

        if self.loud:
            print 'Starting motion.'

        self.resetClock()
        self.currentPos = self.query()

        if logFile:
            #print >>logFile, '# time, servo goal positions (9), servo actual positions (9), robot location (x, y, age)'
            print >>logFile, '# time, servo goal positions (9), robot location (x, y, age)'

        # Reset the robot position, if desired
        if resetFirst:
            self.interpMove(self.query(), POS_FLAT, 3)
            self.interpMove(POS_FLAT, POS_READY, 3)
            #self.interpMove(POS_READY, POS_HALFSTAND, 4)
            self.currentPos = POS_READY
            self.resetClock()

        # Begin with a segment smoothly interpolated between the
        # current position and the motion model.
        if interpBegin is not None:
            self.interpMove(self.currentPos,
                            scaleTime(motionFunction, timeScale),
                            interpBegin * timeScale,
                            logFile, extraLogInfoFn)
            self.currentPos = motionFunction(self.time)

        # Main motion segment
        self.interpMove(scaleTime(motionFunction, timeScale),
                        scaleTime(motionFunction, timeScale),
                        runSeconds * timeScale,
                        logFile, extraLogInfoFn)
        self.currentPos = motionFunction(self.time)

        # End with a segment smoothly interpolated between the
        # motion model and a ready position.
        if interpEnd is not None:
            self.interpMove(scaleTime(motionFunction, timeScale),
                            POS_READY,
                            interpEnd * timeScale,
                            logFile, extraLogInfoFn)

        
    def interpMove(self, start, end, seconds, logFile=None, extraLogInfoFn=None):
        '''Moves between start and end over seconds seconds.  start
        and end may be functions of the time.'''

        self.updateClock()
        
        timeStart = self.time
        timeEnd   = self.time + seconds

        ii = 0
        tlast = self.time
        while self.time < timeEnd:
            #print 'time:', self.time
            ii += 1
            posS = start(self.time) if isinstance(start, FunctionType) else start
            posE =   end(self.time) if isinstance(end,   FunctionType) else end
            goal = lInterp(self.time, [timeStart, timeEnd], posS, posE)
            print goal
            cmdPos = self.commandPosition(goal)
            if logFile:
                extraInfo = ''
                if extraLogInfoFn:
                    extraInfo = extraLogInfoFn()
                print >>logFile, self.time, ' '.join([str(x) for x in cmdPos]),
                #print >>logFile, ' '.join(str(ac.current_position) for ac in self.actuators),
                print >>logFile, extraInfo
                
            #sleep(self.sleep)
            #sleep(float(1)/100)
            self.updateClock()
            secElapsed = self.time - tlast
            tosleep = self.sleep - secElapsed
            #if tosleep > 0:
                #sleep(tosleep)
            self.updateClock()
            tlast = self.time
            
    def resetClock(self):
        '''Resets the robot time to zero'''
        self.time0 = datetime.now()
        self.time  = 0.0

    def updateClock(self):
        '''Updates the Robots clock to the current time'''
        timeDiff  = datetime.now() - self.time0
        self.time = timeDiff.seconds + timeDiff.microseconds/1e6

    def readyPosition(self, persist = False):
        if persist:
            self.resetClock()
            while self.time < 2.0:
                self.commandPosition(POS_READY)
                sleep(.1)
                self.updateClock()
        else:
            self.commandPosition(POS_READY)
            sleep(2)

    def commandPosition(self, position, crop = True, cropWarning = False):
        '''Command the given position

        commandPosition will command the robot to move its servos to
        the given position vector.  This vector is cropped to
        the physical limits of the robot and converted to integer

        Positional arguments:
    position -- A length 8 vector of desired positions.

        Keyword arguments:
        cropWarning -- Whether or not to print a warning if the
                       positions are cropped.  Default: False.
        '''

        if len(position) != self.nServos:
            raise Exception('Expected postion vector of length %d, got %s instead'
                            % (self.nServos, repr(position)))

        if crop:
            goalPosition = self.cropPosition([int(xx) for xx in position], cropWarning)
        else:
            goalPosition = [int(xx) for xx in position]

        if self.loud:
            posstr = ', '.join(['%4d' % xx for xx in goalPosition])
            print '%.2fs -> %s' % (self.time, posstr)
        
        self.commandPos(goalPosition)

        return goalPosition

    def cropPosition(self, position, cropWarning = False):
        '''Crops the given positions to their appropriate min/max values.
        
        Requires a vector of length 9 to be sure the IDs are in the
        assumed order.'''

        if len(position) != self.nServos:
            raise Exception('cropPosition expects a vector of length %d' % self.nServos)

        ret = copy(position)
        for ii in self.expectedIds:
            ret[ii] = max(MIN_BYTE_VAL, min(MAX_BYTE_VAL, ret[ii]))
        
        if cropWarning and ret != position:
            print 'Warning: cropped %s to %s' % (repr(position), repr(ret))
            
        return ret

    def printStatus(self):
        pos = self.query()
        print 'Positions:', ' '.join(['%d:%d' % (ii,pp) for ii,pp in enumerate(pos)])
    
    def __writeCommand(self,command, args=None):
        '''Writes out a command to ArbotiX.
            command -- the command from the constants.py file
            args -- an iterable list of args. Must be castable to a String'''
        commandToWrite = command
        if args is not None:
            for arg in args:
                commandToWrite += str(arg) + ","
        commandToWrite = commandToWrite.strip(",")
        commandToWrite = commandToWrite + COMMAND_END
        print "Command: " + commandToWrite
        self.ser.write(commandToWrite)
    
    def helloBoard(self):
        '''Tests the communication channel with the ArbotiX. Blocks until the
        ArbotiX successfully replies with the hello message.'''
        reply = ''
        self.failedPackets = -1
        while reply != HELLO:
            self.failedPackets += 1
            print "about to write hello"
            self.__writeCommand(HELLO)
            print "wrote command"
            reply = self.ser.readline()
            print "helloReply: " + reply
        print self.failedPackets
    
    def query(self):
        '''Requests information regarding servo positions from ArbotiX. Returns
        a list of length self.numServos representing the servo positions.'''
        self.__writeCommand(QUERY)
        reply = self.ser.readline()
        
        if reply[:2] != QUERY:
            raise Exception("did not receive QUERY")
        
        reply = [int(pos) for pos in reply[2:-2].split(SEPARATOR)]
        if len(reply) != self.numServos:
            raise Exception("invalid reply--expected " + str(self.numServos) + " items but got " + str(len(reply)))
        
        return [int(pos) for pos in reply[2:-2].split(SEPARATOR)]
    
    def commandPos(self, posVector):
        '''Commands ArbotiX to move servos to the given goal position.'''
        if len(posVector) != self.numServos:
            raise Exception("invalid position vector--expected " + str(self.numServos) + " items but got " + str(len(posVector)))
        
        self.__writeCommand(POSITION, posVector)
        reply = self.ser.readline()
        
        if reply[:2] != POSITION:
            raise Exception("did not receive POSITION, instead got\n" +reply +" as reply.")
        
        reply = [int(pos) for pos in reply[2:-2].split(SEPARATOR)]
        if len(reply) != self.numServos:
            raise Exception("invalid reply--expected " + str(self.numServos) + " items but got " + str(len(posVector)))
        
        return reply

    def shimmy(self):
        '''Filler for compatibility with Quadratot'''
        return True