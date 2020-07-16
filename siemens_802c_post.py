 #***************************************************************************
#*                                                                         *
#*   This file is part of the FreeCAD CAx development system.              *
#*                                                                         *
#*   This program is free software; you can redistribute it and/or modify  *
#*   it under the terms of the GNU Lesser General Public License (LGPL)    *
#*   as published by the Free Software Foundation; either version 2 of     *
#*   the License, or (at your option) any later version.                   *
#*   for detail see the LICENCE text file.                                 *
#*                                                                         *
#*   FreeCAD is distributed in the hope that it will be useful,            *
#*   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
#*   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
#*   GNU Lesser General Public License for more details.                   *
#*                                                                         *
#*   You should have received a copy of the GNU Library General Public     *
#*   License along with FreeCAD; if not, write to the Free Software        *
#*   Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  *
#*   USA                                                                   *
#*                                                                         *
#***************************************************************************/
from __future__ import print_function

TOOLTIP='''
This is a postprocessor file for the Path workbench. It is used to
take a pseudo-gcode fragment outputted by a Path object, and output
real GCode suitable for a Tree Journyman 325 3 axis mill with Dynapath 20 controller in MM.
This is a work in progress and very few of the functions available on the Dynapath have been
implemented at this time.
This postprocessor, once placed in the appropriate PathScripts folder, can be used directly
from inside FreeCAD, via the GUI importer or via python scripts with:
'''

import datetime
import os
import re
now = datetime.datetime.now()
from PathScripts import PostUtils
from pprint import pprint

#These globals set common customization preferences
OUTPUT_COMMENTS = True
OUTPUT_HEADER = True
OUTPUT_LINE_NUMBERS = True
SHOW_EDITOR = True
MODAL = False #if true commands are suppressed if the same as previous line.
COMMAND_SPACE = " "
LINENR = 10 #line number starting value
PRECISION = 3

#These globals will be reflected in the Machine configuration of the project
UNITS =                  'G21' #G21 for metric, G20 for us standard
MOTION_MODE =            'G90'    # G90 for absolute moves, G91 for relative
UNITS =                  'G21'    # G21 for metric, G20 for us standard

MACHINE_NAME = "Tree MM"
CORNER_MIN = {'x':-340, 'y':0, 'z':0 }
CORNER_MAX = {'x':340, 'y':-355, 'z':-150 }

#Preamble text will appear at the beginning of the GCODE output file.
PREAMBLE = '''G17
G90 G94
G71
G64
G17
G54
G53 G0 Z0
'''

#Postamble text will appear following the last operation.
POSTAMBLE = '''M09
M05
G80
G40
G17
G90
M30
'''


#Pre operation text will be inserted before every operation
PRE_OPERATION = ''''''

#Post operation text will be inserted after every operation
POST_OPERATION = ''''''

#Tool Change commands will be inserted before a tool change
TOOL_CHANGE = ''''''


# to distinguish python built-in open function from the one declared below
if open.__module__ in ['__builtin__','io']:
    pythonopen = open


def export(objectslist,filename,argstring):
    global UNITS
    for obj in objectslist:
        if not hasattr(obj,"Path"):
            print("the object " + obj.Name + " is not a path. Please select only path and Compounds.")
            return

    print("postprocessing...")
    gcode = ""

    #Find the machine.
    #The user my have overridden post processor defaults in the GUI.  Make sure we're using the current values in the Machine Def.
    myMachine = None
    for pathobj in objectslist:
        if hasattr(pathobj,"MachineName"):
            myMachine = pathobj.MachineName
        if hasattr(pathobj, "MachineUnits"):
            if pathobj.MachineUnits == "Metric":
               UNITS = "G21"
            else:
               UNITS = "G20"
    if myMachine is None:
        print("No machine found in this selection")

    # write header
    if OUTPUT_HEADER:
        basename = os.path.basename(filename).upper().replace('.', '_')
        gcode += "%_N_" + basename + "\n"
        gcode += linenumber() + "; Exported by FreeCAD\n"
        gcode += linenumber() + "; Post Processor: " + __name__ +"\n"

    #Write the preamble
    if OUTPUT_COMMENTS: gcode += linenumber() + "; begin preamble\n"
    for line in PREAMBLE.splitlines(True):
        gcode += linenumber() + line
    # gcode += linenumber() + UNITS + "\n"

    for obj in objectslist:

        #do the pre_op
        if OUTPUT_COMMENTS: gcode += linenumber() + "; begin operation: " + obj.Label + "\n"
        for line in PRE_OPERATION.splitlines(True):
            gcode += linenumber() + line

        gcode += parse(obj)

        #do the post_op
        if OUTPUT_COMMENTS: gcode += linenumber() + "; finish operation: " + obj.Label + "\n"
        for line in POST_OPERATION.splitlines(True):
            gcode += linenumber() + line

    #do the post_amble

    for line in POSTAMBLE.splitlines(True):
        gcode += linenumber() + line

    if SHOW_EDITOR:
        dia = PostUtils.GCodeEditorDialog()
        dia.editor.setText(gcode)
        result = dia.exec_()
        if result:
            final = dia.editor.toPlainText()
        else:
            final = gcode
    else:
        final = gcode

    print("done postprocessing.")

    gfile = pythonopen(filename,"w")
    gfile.write(final)
    gfile.close()


def linenumber():
    global LINENR
    if OUTPUT_LINE_NUMBERS == True:
        LINENR += 5
        return "N" + str(LINENR) + " "
    return ""

def format_outstring(strTbl):
  global COMMAND_SPACE
  # construct the line for the final output
  s = ""
  for w in strTbl:
    s += w + COMMAND_SPACE
  s = s.strip()
  return s

def parse(pathobj):
    out = ""
    lastcommand = None

    #params = ['X','Y','Z','A','B','I','J','K','F','S'] #This list control the order of parameters
    params = ['X','Y','Z','A','B','I','J','F','S','T','Q','R','L'] #linuxcnc doesn't want K properties on XY plane  Arcs need work.

    if hasattr(pathobj,"Group"): #We have a compound or project.
        if OUTPUT_COMMENTS: out += linenumber() + "; compound: " + pathobj.Label + "\n"
        for p in pathobj.Group:
            out += parse(p)
        return out
    else: #parsing simple path

        if not hasattr(pathobj,"Path"): #groups might contain non-path things like stock.
            return out

        for c in pathobj.Path.Commands:
            outstring = []
            command = c.Name
            print("Command: %s" % command)
            if not command.startswith('('):
                outstring.append(command)
            # if modal: only print the command if it is not the same as the last one
            if MODAL == True:
                if command == lastcommand:
                    outstring.pop(0)


            # Now add the remaining parameters in order
            for param in params:
                if param in c.Parameters:
                    if param == 'F':
                        outstring.append(param + format(c.Parameters['F'], '.0f'))
                    elif param == 'S':
                        outstring.append(param + format(c.Parameters[param], '.0f'))
                    elif param == 'T':
                        outstring.append(param + format(c.Parameters['T'], '.0f'))
                    else:
                        outstring.append(param + format(c.Parameters[param], '.3f'))

            # store the latest command
            lastcommand = command

            # Check for Tool Change:
            if command == 'M6':
                if OUTPUT_COMMENTS: out += linenumber() + "; begin toolchange\n"
                for line in TOOL_CHANGE.splitlines(True):
                    out += linenumber() + line

            if command == "message":
                if OUTPUT_COMMENTS == False:
                    out = []
                else:
                    outstring.pop(0) #remove the command

            if command in ('G81', 'G82', 'G83'):
                out += linenumber() + "; Drill Seq\n"
                out += drill_translate(outstring, command, c.Parameters)
                del(outstring[:])
                outstring = []

            #prepend a line number and append a newline
            if len(outstring) >= 1:
                if OUTPUT_LINE_NUMBERS:
                    outstring.insert(0,(linenumber()))

                #append the line to the final output
                for w in outstring:
                    out += w + COMMAND_SPACE
                out = out.strip() + "\n"

        return out

def drill_translate(outstring, cmd, params):

  pprint(params)

  trBuff = ""

  if cmd == 'G83':
      trBuff += linenumber() + "G0 X" + format(params['X'], '.0f') + " "
      trBuff += "Y" + format(params['Y'], '.0f') + "\n"
      trBuff += linenumber() + "R101=" + "0 " + "R102=" + format(params['R'], '.0f')+ "\n"
      trBuff += linenumber() + "R103=" + "0 " + "R104=" + format(params['Z'], '.0f') + "\n"
      trBuff += linenumber() + "R105=" + "0 " + "R107=" + format(params['F'], '.0f') + "\n"
      trBuff += linenumber() + "R108=" + format(params['Q'], '.0f') + " R109=" + "0" + "\n"
      trBuff += linenumber() + "R110=" + format(params['Q'], '.0f') + " R111=" + "0" + "\n"
      trBuff += linenumber() + "R127=1.000\n" + linenumber() + "LCYC83\n"
#  drill_Speed = params['F'] * SPEED_MULTIPLIER
#  if cmd == 'G83':
#    drill_Step = params['Q']
#  elif cmd == 'G82':
#    drill_DwellTime = params['P']
#
#  if MOTION_MODE == 'G91':
#    trBuff += linenumber() + "G90" + "\n" # Force des deplacements en coordonnees absolues pendant les cycles
#
#  # Mouvement(s) preliminaire(s))
#  if CURRENT_Z < RETRACT_Z:
#    trBuff += linenumber() + 'G0 Z' + format(RETRACT_Z, strFormat) + "\n"
#  trBuff += linenumber() + 'G0 X' + format(drill_X, strFormat) + ' Y' + format(drill_Y, strFormat) + "\n"
#  if CURRENT_Z > RETRACT_Z:
#    trBuff += linenumber() + 'G0 Z' + format(CURRENT_Z, strFormat) + "\n"

#  # Mouvement de percage
#  if cmd in ('G81', 'G82'):
#    trBuff += linenumber() + 'G1 Z' + format(drill_Z, strFormat) + ' F' + format(drill_Speed, '.2f') + "\n"
#    # Temporisation eventuelle
#    if cmd == 'G82':
#      trBuff += linenumber() + 'G4 P' + str(drill_DwellTime) + "\n"
#    # Sortie de percage
#    trBuff += linenumber() + 'G0 Z' + format(RETRACT_Z, strFormat) + "\n"
#  else: # 'G83'
#    next_Stop_Z = RETRACT_Z - drill_Step
#    while 1:
#      if next_Stop_Z > drill_Z:
#        trBuff += linenumber() + 'G1 Z' + format(next_Stop_Z, strFormat) + ' F' + format(drill_Speed, '.2f') + "\n"
#        trBuff += linenumber() + 'G0 Z' + format(RETRACT_Z, strFormat) + "\n"
#        next_Stop_Z -= drill_Step
#      else:
#        trBuff += linenumber() + 'G1 Z' + format(drill_Z, strFormat) + ' F' + format(drill_Speed, '.2f') + "\n"
#        trBuff += linenumber() + 'G0 Z' + format(RETRACT_Z, strFormat) + "\n"
#        break
#
#  if MOTION_MODE == 'G91':
#    trBuff += linenumber() + 'G91' # Restore le mode de deplacement relatif
#
  return trBuff

print(__name__ + " gcode postprocessor loaded.")

