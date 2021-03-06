#copyright (c) 2007-8, Playful Invention Company
#Copyright (c) 2008-13, Walter Bender
#Copyright (c) 2013 Alan Aguiar

#Permission is hereby granted, free of charge, to any person obtaining a copy
#of this software and associated documentation files (the "Software"), to deal
#in the Software without restriction, including without limitation the rights
#to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
#copies of the Software, and to permit persons to whom the Software is
#furnished to do so, subject to the following conditions:

#The above copyright notice and this permission notice shall be included in
#all copies or substantial portions of the Software.

#THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
#AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
#OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
#THE SOFTWARE.

import gtk
import gobject
import gconf
import dbus
import cairo
import pickle
import subprocess
import os
import string
from gettext import gettext as _

try:
    OLD_SUGAR_SYSTEM = False
    import json
    json.dumps
    from json import load as jload
    from json import dump as jdump
except (ImportError, AttributeError):
    try:
        import simplejson as json
        from simplejson import load as jload
        from simplejson import dump as jdump
    except:
        OLD_SUGAR_SYSTEM = True
from StringIO import StringIO

from taconstants import (HIT_HIDE, HIT_SHOW, XO1, XO15, XO175, XO4, UNKNOWN,
                         MAGICNUMBER, SUFFIX)

import logging
_logger = logging.getLogger('turtleart-activity')


FIRST_TIME = True


def debug_output(message_string, running_sugar=False):
    ''' unified debugging output '''
    if running_sugar:
        _logger.debug(message_string)
    else:
        print(message_string)


def error_output(message_string, running_sugar=False):
    ''' unified debugging output '''
    if running_sugar:
        _logger.error(message_string)
    else:
        print(message_string)


class pythonerror(Exception):

    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)


def convert(x, fn, try_ord=True):
    '''
    The strategy for mixing numbers and strings is to first try
    converting the string to a float; then if the string is a single
    character, try converting it to an ord; finally, just treat it as a
    string. Numbers appended to strings are first treated as ints, then
    floats.
    '''
    try:
        return fn(x)
    except ValueError:
        if try_ord:
            xx, flag = chr_to_ord(x)
            if flag:
                return fn(xx)
        return x


def chr_to_ord(x):
    ''' Try to comvert a string to an ord '''
    if strtype(x) and len(x) == 1:
        try:
            return ord(x[0]), True
        except ValueError:
            return x, False
    return x, False


def strtype(x):
    ''' Is x a string type? '''
    if isinstance(x, (str, unicode)):
        return True
    return False


def increment_name(name):
    ''' If name is of the form foo_1, change it to foo_2. Otherwise,
    return name_1'''
    if '_' in name:
        parts = name.split('_')
        try:
            i = int(parts[-1])
            i += 1
            parts[-1] = str(i)
            newname = string.join(parts, '_')
        except ValueError:
            newname = '%s_1' % (name)
    else:
        newname = '%s_1' % (name)
    return newname


def magnitude(pos):
    ''' Calculate the magnitude of the distance between to blocks. '''
    x, y = pos
    return x * x + y * y


def json_load(text):
    ''' Load JSON data using what ever resources are available. '''
    if OLD_SUGAR_SYSTEM is True:
        listdata = json.read(text)
    else:
        # Remove MAGIC NUMBER, if present, and leading whitespace
        if text[0:2] == MAGICNUMBER:
            clean_text = text[2:].lstrip()
        else:
            clean_text = text.lstrip()
        # Strip out trailing whitespace, nulls, and newlines
        clean_text = clean_text.replace('\12', '')
        clean_text = clean_text.replace('\00', '')
        clean_text = clean_text.rstrip()
        # Look for missing ']'s
        left_count = clean_text.count('[')
        right_count = clean_text.count(']')
        while left_count > right_count:
            clean_text += ']'
            right_count = clean_text.count(']')
        io = StringIO(clean_text)
        try:
            listdata = jload(io)
        except ValueError:
            # Assume that text is ascii list
            listdata = text.split()
            for i, value in enumerate(listdata):
                listdata[i] = convert(value, float)
    # json converts tuples to lists, so we need to convert back,
    return _tuplify(listdata)


def find_hat(data):
    ''' Find a hat in a stack '''
    for i, blk in enumerate(data):
        if _to_str(blk[1]) == 'hat':
            return i
    return None


def _to_str(text):
    ''' Convert whatever to a str type '''
    if isinstance(text, unicode):
        return text.encode('ascii', 'replace')
    elif isinstance(text, str):
        return text
    else:
        try:
            return str(text)
        except ValueError:
            return ''


def hat_on_top(data):
    ''' Move the hat block in a stack to the top '''
    hat = find_hat(data)
    if hat is None or hat == 0:
        return data

    data_was_tuple = False
    if isinstance(data, tuple):
        data_was_tuple = True
        data = listify(data)

    # First put the vertical flow together
    stack = [hat]
    sort = [hat]
    sorted_data = [[0, 'hat', data[hat][2], data[hat][3], []]]
    i = 1
    while len(stack) > 0:
        branch = stack[0]
        stack.remove(stack[0])
        if branch is None:
            continue
        else:
            blk = data[branch]

        if branch != hat:
            sort.append(blk[0])
            sorted_data.append([i, blk[1], 0, 0, []])
            i += 1

        while blk[4][-1] is not None:
            cblk = blk[4][-1]
            sort.append(cblk)
            name = data[cblk][1]
            sorted_data.append([i, name, 0, 0, []])
            if isinstance(name, list):
                name = name[0]
            # Some blocks have multiple branches
            if _to_str(name) in ['repeat', 'forever', 'while', 'until',
                                 'ifelse', 'if', 'sandwichclamp',
                                 'sandwichclampcollapsed']:
                stack.append(data[cblk][4][-2])
            if _to_str(name) in ['ifelse']:
                stack.append(data[cblk][4][-3])
            i += 1
            blk = data[cblk]

    # Then add the argument blocks
    for blk in data:
        if blk[0] in sort:
            continue
        sort.append(blk[0])
        sorted_data.append([i, blk[1], 0, 0, []])
        i += 1

    # Then add the connections
    for i, blk in enumerate(sort):
        for j in data[blk][4]:
            if j is None:
                sorted_data[i][4].append(None)
            else:
                sorted_data[i][4].append(sort.index(j))

    if data_was_tuple:
        return _tuplify(sorted_data)
    return sorted_data


def _tuplify(tup):
    ''' Convert to tuples '''
    if not isinstance(tup, list):
        return tup
    return tuple(map(_tuplify, tup))


def listify(tup):
    ''' Convert to list '''
    if not isinstance(tup, tuple):
        return tup
    return list(map(listify, tup))


def get_id(connection):
    ''' Get a connection block ID. '''
    if connection is not None and hasattr(connection, 'id'):
        return connection.id
    return None


def json_dump(data):
    ''' Save data using available JSON tools. '''
    if OLD_SUGAR_SYSTEM is True:
        return json.write(data)
    else:
        io = StringIO()
        jdump(data, io)
        return io.getvalue()


def get_load_name(filefilter, load_save_folder):
    ''' Open a load file dialog. '''
    dialog = gtk.FileChooserDialog(
        _('Load...'), None,
        gtk.FILE_CHOOSER_ACTION_OPEN, (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                                       gtk.STOCK_OPEN, gtk.RESPONSE_OK))
    dialog.set_default_response(gtk.RESPONSE_OK)
    return do_dialog(dialog, filefilter, load_save_folder)


def get_save_name(filefilter, load_save_folder, save_file_name):
    ''' Open a save file dialog. '''
    dialog = gtk.FileChooserDialog(
        _('Save...'), None,
        gtk.FILE_CHOOSER_ACTION_SAVE, (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                                       gtk.STOCK_SAVE, gtk.RESPONSE_OK))
    dialog.set_default_response(gtk.RESPONSE_OK)
    if filefilter in ['.png', '.svg', '.lg']:
        suffix = filefilter
    else:
        suffix = SUFFIX[1]
    if save_file_name is not None:
        if not save_file_name.endswith(suffix):
            save_file_name = save_file_name + suffix
        dialog.set_current_name(save_file_name)
    return do_dialog(dialog, filefilter, load_save_folder)


def chooser_dialog(parent_window, filter, action):
    ''' Choose an object from the datastore and take some action '''
    from sugar.graphics.objectchooser import ObjectChooser

    chooser = None
    dsobject = None
    cleanup_needed = False
    try:
        chooser = ObjectChooser(parent=parent_window, what_filter=filter)
    except TypeError:  # Old-syle Sugar chooser
        chooser = ObjectChooser(
            None,
            parent_window,
            gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT)
        cleanup_needed = True

    if chooser is not None:
        result = chooser.run()
        if result == gtk.RESPONSE_ACCEPT:
            dsobject = chooser.get_selected_object()
        if cleanup_needed:
            chooser.destroy()
            del chooser
    gobject.idle_add(action, dsobject)


def data_from_file(ta_file):
    ''' Open the .ta file, ignoring any .png file that might be present. '''
    file_handle = open(ta_file, 'r')
    #
    # We try to maintain read-compatibility with all versions of Turtle Art.
    # Try pickle first; then different versions of json.
    #
    try:
        data = pickle.load(file_handle)
    except:
        # Rewind necessary because of failed pickle.load attempt
        file_handle.seek(0)
        text = file_handle.read()
        data = data_from_string(text)
    file_handle.close()
    return data


def data_from_string(text):
    ''' JSON load data from a string. '''
    if isinstance(text, str):
        return json_load(text.replace(']],\n', ']], '))
    elif isinstance(text, unicode):
        text = text.encode('ascii', 'replace')
        return json_load(text.replace(']],\n', ']], '))
    else:
        print 'type error (%s) in data_from_string' % (type(text))
        return None


def data_to_file(data, ta_file):
    ''' Write data to a file. '''
    file_handle = file(ta_file, 'w')
    file_handle.write(data_to_string(data))
    file_handle.close()


def data_to_string(data):
    ''' JSON dump a string. '''
    return json_dump(data).replace(']], ', ']],\n')


def do_dialog(dialog, suffix, load_save_folder):
    ''' Open a file dialog. '''
    result = None
    file_filter = gtk.FileFilter()
    file_filter.add_pattern('*' + suffix)
    file_filter.set_name('Turtle Art')
    dialog.add_filter(file_filter)
    dialog.set_current_folder(load_save_folder)
    response = dialog.run()
    if response == gtk.RESPONSE_OK:
        result = dialog.get_filename()
        load_save_folder = dialog.get_current_folder()
    dialog.destroy()
    return result, load_save_folder


def save_picture(canvas, file_name):
    ''' Save the canvas to a file '''
    x_surface = canvas.canvas.get_target()
    img_surface = cairo.ImageSurface(cairo.FORMAT_RGB24,
                                     canvas.width, canvas.height)
    cr = cairo.Context(img_surface)
    cr.set_source_surface(x_surface)
    cr.paint()
    if isinstance(file_name, unicode):
        img_surface.write_to_png(str(file_name.encode('ascii', 'replace')))
    else:
        img_surface.write_to_png(str(file_name))


def get_canvas_data(canvas):
    ''' Get pixel data from the turtle canvas '''
    x_surface = canvas.canvas.get_target()
    img_surface = cairo.ImageSurface(cairo.FORMAT_RGB24,
                                     canvas.width, canvas.height)
    cr = cairo.Context(img_surface)
    cr.set_source_surface(x_surface)
    cr.paint()
    return img_surface.get_data()


def get_pixbuf_from_journal(dsobject, w, h):
    ''' Load a pixbuf from a Journal object. '''
    try:
        pixbuf = gtk.gdk.pixbuf_new_from_file_at_size(dsobject.file_path,
                                                      int(w), int(h))
    except:
        try:
            pixbufloader = \
                gtk.gdk.pixbuf_loader_new_with_mime_type('image/png')
            pixbufloader.set_size(min(300, int(w)), min(225, int(h)))
            pixbufloader.write(dsobject.metadata['preview'])
            pixbufloader.close()
            pixbuf = pixbufloader.get_pixbuf()
        except:
            pixbuf = None
    return pixbuf


def get_path(activity, subpath):
    ''' Find a Rainbow-approved place for temporary files. '''
    if hasattr(activity, "get_activity_root"):
        return(os.path.join(activity.get_activity_root(), subpath))
    else:
        # Early versions of Sugar didn't support get_activity_root()
        return(os.path.join(os.environ['HOME'], '.sugar/default',
                            'org.laptop.TurtleArtActivity', subpath))


def image_to_base64(image_path, tmp_path):
    ''' Convert an image to base64-encoded data '''
    base64 = os.path.join(tmp_path, 'base64tmp')
    cmd = 'base64 <' + image_path + ' >' + base64
    subprocess.check_call(cmd, shell=True)
    file_handle = open(base64, 'r')
    data = file_handle.read()
    file_handle.close()
    os.remove(base64)
    return data


def base64_to_image(data, path_name):
    ''' Convert base64-encoded data to an image '''
    base64 = os.path.join(path_name, 'base64tmp')
    file_handle = open(base64, 'w')
    file_handle.write(data)
    file_handle.close()
    file_name = os.path.join(path_name, 'imagetmp.png')
    cmd = 'base64 -d <' + base64 + '>' + file_name
    subprocess.check_call(cmd, shell=True)
    return file_name


def movie_media_type(name):
    ''' Is it movie media? '''
    return name.lower().endswith(('.ogv', '.vob', '.mp4', '.wmv', '.mov',
                                  '.mpeg', '.ogg', '.webm'))


def audio_media_type(name):
    ''' Is it audio media? '''
    return name.lower().endswith(('.oga', '.m4a'))


def image_media_type(name):
    ''' Is it image media? '''
    return name.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.tiff',
                                  '.tif', '.svg'))


def text_media_type(name):
    ''' Is it text media? '''
    return name.lower().endswith(('.txt', '.py', '.lg', '.rtf'))


def round_int(num):
    ''' Remove trailing decimal places if number is an int '''
    try:
        float(num)
    except TypeError:
        raise pythonerror('#syntaxerror')

    if int(float(num)) == num:
        return int(num)
    else:
        if float(num) < 0:
            nn = int((float(num) - 0.005) * 100) / 100.
        else:
            nn = int((float(num) + 0.005) * 100) / 100.
        if int(float(nn)) == nn:
            return int(nn)
        return nn


def calc_image_size(spr):
    ''' Calculate the maximum size for placing an image onto a sprite. '''
    return int(max(spr.label_safe_width(), 1)), \
        int(max(spr.label_safe_height(), 1))


def restore_clamp(top):
    ''' Restore the blocks in a sandwich clamp. '''
    if top is None:
        return

    if top.name == 'sandwichclampcollapsed':
        y1 = top.docks[2][3]
        if top.connections[1] is not None:
            for blk in find_group(top.connections[1]):
                blk.spr.restore()
                blk.status = None

            # If you come across a 'sandwichclampcollapsed', do not
            # restore its clamp
            for blk in find_group(top.connections[1]):
                if blk.name == 'sandwichclampcollapsed':
                    if blk.connections[1] is not None:
                        for b in find_group(blk.connections[1]):
                            b.spr.hide()
                            b.status = 'collapsed'

        bot = top.connections[2]
        top.name = 'sandwichclamp'
        top.spr.set_label('')
        top.resize()
        top.svg.set_hide(True)
        top.refresh()
        y2 = top.docks[2][3]
        dy = y2 - y1
        if bot is not None:
            for blk in find_group(bot):
                blk.spr.move_relative((0, dy))
        if top.connections[1] is not None:
            # Make sure stack is aligned to dock
            x1, y1 = top.connections[1].spr.get_xy()
            x1 += top.connections[1].docks[0][2]
            y1 += top.connections[1].docks[0][3]
            x2, y2 = top.spr.get_xy()
            x2 += top.docks[1][2]
            y2 += top.docks[1][3]
            if x1 != x2 or y1 != y2:
                for blk in find_group(top.connections[1]):
                    blk.spr.move_relative((x2 - x1, y2 - y1))
        return


def collapse_clamp(top, transform=True):
    ''' Hide all the blocks in the clamp. '''
    if top is None or top.spr is None:
        return

    if top.name in ['sandwichclampcollapsed', 'sandwichclamp']:
        y1 = top.docks[2][3]
        if top.connections[1] is not None:
            for blk in find_group(top.connections[1]):
                blk.spr.hide()
                blk.status = 'collapsed'
        if transform:
            bot = top.connections[2]
            top.name = 'sandwichclampcollapsed'
            top.spr.set_label(_('click to open'))
            top.reset_y()
            top.resize()
            top.svg.set_hide(False)
            top.refresh()
            y2 = top.docks[2][3]
            dy = y2 - y1
            if bot is not None:
                for blk in find_group(bot):
                    blk.spr.move_relative((0, dy))
        return


def hide_button_hit(spr, x, y):
    ''' Did the sprite's hide (contract) button get hit? '''
    red, green, blue, alpha = spr.get_pixel((x, y))
    if red == HIT_HIDE:
        return True
    else:
        return False


def show_button_hit(spr, x, y):
    ''' Did the sprite's show (expand) button get hit? '''
    red, green, blue, alpha = spr.get_pixel((x, y))
    if green == HIT_SHOW:
        return True
    else:
        return False


def numeric_arg(value):
    ''' Dock test: looking for a numeric value '''
    if isinstance(convert(value, float), float):
        return True
    return False


def zero_arg(value):
    ''' Dock test: looking for a zero argument '''
    if numeric_arg(value):
        if convert(value, float) == 0:
            return True
    return False


def neg_arg(value):
    ''' Dock test: looking for a negative argument '''
    if numeric_arg(value):
        if convert(value, float) < 0:
            return True
    return False


def journal_check(blk1, blk2, dock1, dock2):
    ''' Dock blocks only if arg is Journal block '''
    if blk1 is None or blk2 is None:
        return True
    if (blk1.name == 'skin' and dock1 == 1) and blk2.name != 'journal':
        return False
    if (blk2.name == 'skin' and dock2 == 1) and blk1.name != 'journal':
        return False
    return True


def arithmetic_check(blk1, blk2, dock1, dock2):
    ''' Dock strings only if they convert to numbers. Avoid /0 and root(-1)'''
    if blk1 is None or blk2 is None:
        return True
    if blk1.name in ['sqrt', 'number', 'string'] and\
       blk2.name in ['sqrt', 'number', 'string']:
        if blk1.name == 'number' or blk1.name == 'string':
            if not numeric_arg(blk1.values[0]) or neg_arg(blk1.values[0]):
                return False
        elif blk2.name == 'number' or blk2.name == 'string':
            if not numeric_arg(blk2.values[0]) or neg_arg(blk2.values[0]):
                return False
    elif blk1.name in ['division2', 'number', 'string'] and \
            blk2.name in ['division2', 'number', 'string']:
        if blk1.name == 'number' or blk1.name == 'string':
            if not numeric_arg(blk1.values[0]):
                return False
            if dock2 == 2 and zero_arg(blk1.values[0]):
                return False
        elif blk2.name == 'number' or blk2.name == 'string':
            if not numeric_arg(blk2.values[0]):
                return False
            if dock1 == 2 and zero_arg(blk2.values[0]):
                return False
    elif blk1.name \
            in ['product2', 'minus2', 'random', 'remainder2', 'string'] and \
            blk2.name \
            in ['product2', 'minus2', 'random', 'remainder2', 'string']:
        if blk1.name == 'string':
            if not numeric_arg(blk1.values[0]):
                return False
        elif blk1.name == 'string':
            if not numeric_arg(blk2.values[0]):
                return False
    elif blk1.name in ['greater2', 'less2'] and blk2.name == 'string':
        # Non-numeric stings are OK only if both args are strings;
        # Lots of test conditions...
        if dock1 == 1 and blk1.connections[2] is not None:
            if blk1.connections[2].name == 'number':
                if not numeric_arg(blk2.values[0]):
                    return False
        elif dock1 == 2 and blk1.connections[1] is not None:
            if blk1.connections[1].name == 'number':
                if not numeric_arg(blk2.values[0]):
                    return False
    elif blk2.name in ['greater2', 'less2'] and blk1.name == 'string':
        if dock2 == 1 and blk2.connections[2] is not None:
            if blk2.connections[2].name == 'number':
                if not numeric_arg(blk1.values[0]):
                    return False
        elif dock2 == 2 and blk2.connections[1] is not None:
            if blk2.connections[1].name == 'number':
                if not numeric_arg(blk1.values[0]):
                    return False
    elif blk1.name in ['greater2', 'less2'] and blk2.name == 'number':
        if dock1 == 1 and blk1.connections[2] is not None:
            if blk1.connections[2].name == 'string':
                if not numeric_arg(blk1.connections[2].values[0]):
                    return False
        elif dock1 == 2 and blk1.connections[1] is not None:
            if blk1.connections[1].name == 'string':
                if not numeric_arg(blk1.connections[1].values[0]):
                    return False
    elif blk2.name in ['greater2', 'less2'] and blk1.name == 'number':
        if dock2 == 1 and blk2.connections[2] is not None:
            if blk2.connections[2].name == 'string':
                if not numeric_arg(blk2.connections[2].values[0]):
                    return False
        elif dock2 == 2 and blk2.connections[1] is not None:
            if blk2.connections[1].name == 'string':
                if not numeric_arg(blk2.connections[1].values[0]):
                    return False
    return True


def xy(event):
    ''' Where is the mouse event? '''
    return map(int, event.get_coords())


# Utilities related to finding blocks in stacks.


def find_block_to_run(blk):
    ''' Find a stack to run (any stack without a 'def action'on the top). '''
    top = find_top_block(blk)
    if blk == top and blk.name[0:3] is not 'def':
        return True
    else:
        return False


def find_top_block(blk):
    ''' Find the top block in a stack. '''
    if blk is None:
        return None
    if blk.connections is None:
        return blk
    if len(blk.connections) == 0:
        return blk
    while blk.connections[0] is not None:
        blk = blk.connections[0]
    return blk


def find_bot_block(blk):
    ''' Find the bottom block in a stack. '''
    if blk is None:
        return None
    if blk.connections is None:
        return blk
    if len(blk.connections) == 0:
        return blk
    while blk.connections[-1] is not None:
        blk = blk.connections[-1]
    return blk


def find_start_stack(blk):
    ''' Find a stack with a 'start' block on top. '''
    if blk is None:
        return False
    if find_top_block(blk).name == 'start':
        return True
    else:
        return False


def find_group(blk):
    ''' Find the connected group of block in a stack. '''
    if blk is None:
        return []
    group = [blk]
    if blk.connections is not None:
        for cblk in blk.connections[1:]:
            if cblk is not None:
                group.extend(find_group(cblk))
    return group


def find_blk_below(blk, namelist):
    ''' Find a specific block below this block. '''
    if blk is None or len(blk.connections) == 0:
        return
    if not isinstance(namelist, list):
        namelist = [namelist]
    group = find_group(blk)
    for gblk in group:
        if gblk.name in namelist:
            return gblk
    return None


def get_hardware():
    ''' Determine whether we are using XO 1.0, 1.5, ... or 'unknown'
    hardware '''
    version = _get_dmi('product_version')
    # product = _get_dmi('product_name')
    if version is None:
        hwinfo_path = '/bin/olpc-hwinfo'
        if os.path.exists(hwinfo_path) and os.access(hwinfo_path, os.X_OK):
            model = check_output([hwinfo_path, 'model'], 'unknown hardware')
            version = model.strip()
    if version == '1':
        return XO1
    elif version == '1.5':
        return XO15
    elif version == '1.75':
        return XO175
    elif version == '4':
        return XO4
    else:
        # Some systems (e.g. ARM) don't have dmi info
        if os.path.exists('/sys/devices/platform/lis3lv02d/position'):
            return XO175
        elif os.path.exists('/etc/olpc-release'):
            return XO1
        else:
            return UNKNOWN


def _get_dmi(node):
    ''' The desktop management interface should be a reliable source
    for product and version information. '''
    path = os.path.join('/sys/class/dmi/id', node)
    try:
        return open(path).readline().strip()
    except:
        return None


def get_screen_dpi():
    ''' Return screen DPI '''
    xft_dpi = gtk.settings_get_default().get_property('gtk-xft-dpi')
    dpi = float(xft_dpi / 1024)
    return dpi


def check_output(command, warning):
    ''' Workaround for old systems without subprocess.check_output'''
    if hasattr(subprocess, 'check_output'):
        try:
            output = subprocess.check_output(command)
        except subprocess.CalledProcessError:
            print(warning)
            return None
    else:
        import commands

        cmd = ''
        for c in command:
            cmd += c
            cmd += ' '
        (status, output) = commands.getstatusoutput(cmd)
        if status != 0:
            print(warning)
            return None
    return output


def power_manager_off(status):
    '''
    Power management in Sugar
         power_manager_off(True) --> Disable power manager
         power_manager_off(False) --> Use custom power manager
    '''
    global FIRST_TIME

    OHM_SERVICE_NAME = 'org.freedesktop.ohm'
    OHM_SERVICE_PATH = '/org/freedesktop/ohm/Keystore'
    OHM_SERVICE_IFACE = 'org.freedesktop.ohm.Keystore'
    PATH = '/etc/powerd/flags/inhibit-suspend'

    client = gconf.client_get_default()

    ACTUAL_POWER = True

    if FIRST_TIME:
        ACTUAL_POWER = client.get_bool('/desktop/sugar/power/automatic')
        FIRST_TIME = False

    if status:
        VALUE = False
    else:
        VALUE = ACTUAL_POWER

    try:
        client.set_bool('/desktop/sugar/power/automatic', VALUE)
    except gconf.GError:
        pass

    bus = dbus.SystemBus()
    try:
        proxy = bus.get_object(OHM_SERVICE_NAME, OHM_SERVICE_PATH)
        keystore = dbus.Interface(proxy, OHM_SERVICE_IFACE)
        keystore.SetKey('suspend.automatic_pm', bool(VALUE))
    except dbus.exceptions.DBusException:
        if status:
            try:
                fd = open(PATH, 'w')
                fd.close()
            except IOError:
                pass
        elif ACTUAL_POWER:
            try:
                os.remove(PATH)
            except OSError:
                pass
