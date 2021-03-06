# Copyright (C) 2006-2007 Red Hat, Inc.
# Copyright (C) 2010 Collabora Ltd. <http://www.collabora.co.uk/>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

import logging

import gobject
import gconf
import dbus
from telepathy.client import Connection
from telepathy.interfaces import CONNECTION

from xocolor import XoColor
import connection_watcher


CONNECTION_INTERFACE_BUDDY_INFO = 'org.laptop.Telepathy.BuddyInfo'

_owner_instance = None


class BaseBuddyModel(gobject.GObject):
    __gtype_name__ = 'SugarBaseBuddyModel'

    def __init__(self, **kwargs):
        self._key = None
        self._nick = None
        self._color = None
        self._tags = None
        self._current_activity = None

        gobject.GObject.__init__(self, **kwargs)

    def get_nick(self):
        return self._nick

    def set_nick(self, nick):
        self._nick = nick

    nick = gobject.property(type=object, getter=get_nick, setter=set_nick)

    def get_key(self):
        return self._key

    def set_key(self, key):
        self._key = key

    key = gobject.property(type=object, getter=get_key, setter=set_key)

    def get_color(self):
        return self._color

    def set_color(self, color):
        self._color = color

    color = gobject.property(type=object, getter=get_color, setter=set_color)

    def get_tags(self):
        return self._tags

    tags = gobject.property(type=object, getter=get_tags)

    def get_current_activity(self):
        return self._current_activity

    def set_current_activity(self, current_activity):
        if self._current_activity != current_activity:
            self._current_activity = current_activity
            self.notify('current-activity')

    current_activity = gobject.property(type=object,
                                        getter=get_current_activity,
                                        setter=set_current_activity)

    def is_owner(self):
        raise NotImplementedError


class OwnerBuddyModel(BaseBuddyModel):
    __gtype_name__ = 'SugarOwnerBuddyModel'

    def __init__(self):
        BaseBuddyModel.__init__(self)

        #client = gconf.client_get_default()
        #self.props.nick = client.get_string('/desktop/sugar/user/nick')
        self.props.nick = "rgs"
        #color = client.get_string('/desktop/sugar/user/color')
        self.props.color = XoColor(None)

        #self.props.key = get_profile().pubkey
        self.props.key = "foobar"

        self.connect('notify::nick', self.__property_changed_cb)
        self.connect('notify::color', self.__property_changed_cb)
        self.connect('notify::current-activity',
                     self.__current_activity_changed_cb)

        bus = dbus.SessionBus()
        bus.add_signal_receiver(
                self.__name_owner_changed_cb,
                signal_name='NameOwnerChanged',
                dbus_interface='org.freedesktop.DBus')

        bus_object = bus.get_object(dbus.BUS_DAEMON_NAME, dbus.BUS_DAEMON_PATH)
        for service in bus_object.ListNames(
                dbus_interface=dbus.BUS_DAEMON_IFACE):
            if service.startswith(CONNECTION + '.'):
                path = '/%s' % service.replace('.', '/')
                Connection(service, path, bus,
                           ready_handler=self.__connection_ready_cb)

    def __connection_ready_cb(self, connection):
        self._sync_properties_on_connection(connection)

    def __name_owner_changed_cb(self, name, old, new):
        if name.startswith(CONNECTION + '.') and not old and new:
            path = '/' + name.replace('.', '/')
            Connection(name, path, ready_handler=self.__connection_ready_cb)

    def __property_changed_cb(self, buddy, pspec):
        self._sync_properties()

    def __current_activity_changed_cb(self, buddy, pspec):
        conn_watcher = connection_watcher.get_instance()
        for connection in conn_watcher.get_connections():
            if self.props.current_activity is not None:
                activity_id = self.props.current_activity.activity_id
                room_handle = self.props.current_activity.room_handle
            else:
                activity_id = ''
                room_handle = 0

            connection[CONNECTION_INTERFACE_BUDDY_INFO].SetCurrentActivity(
                activity_id,
                room_handle,
                reply_handler=self.__set_current_activity_cb,
                error_handler=self.__error_handler_cb)

    def __set_current_activity_cb(self):
        logging.debug('__set_current_activity_cb')

    def _sync_properties(self):
        conn_watcher = connection_watcher.get_instance()
        for connection in conn_watcher.get_connections():
            self._sync_properties_on_connection(connection)

    def _sync_properties_on_connection(self, connection):
        if CONNECTION_INTERFACE_BUDDY_INFO in connection:
            properties = {}
            if self.props.key is not None:
                properties['key'] = dbus.ByteArray(self.props.key)
            if self.props.color is not None:
                properties['color'] = self.props.color.to_string()

            logging.debug('calling SetProperties with %r', properties)
            connection[CONNECTION_INTERFACE_BUDDY_INFO].SetProperties(
                properties,
                reply_handler=self.__set_properties_cb,
                error_handler=self.__error_handler_cb)

    def __set_properties_cb(self):
        logging.debug('__set_properties_cb')

    def __error_handler_cb(self, error):
        raise RuntimeError(error)

    def __connection_added_cb(self, conn_watcher, connection):
        self._sync_properties_on_connection(connection)

    def is_owner(self):
        return True


def get_owner_instance():
    global _owner_instance
    if _owner_instance is None:
        _owner_instance = OwnerBuddyModel()
    return _owner_instance


class BuddyModel(BaseBuddyModel):
    __gtype_name__ = 'SugarBuddyModel'

    def __init__(self, **kwargs):

        self._account = None
        self._contact_id = None
        self._handle = None

        BaseBuddyModel.__init__(self, **kwargs)

    def is_owner(self):
        return False

    def get_account(self):
        return self._account

    def set_account(self, account):
        self._account = account

    account = gobject.property(type=object, getter=get_account,
                               setter=set_account)

    def get_contact_id(self):
        return self._contact_id

    def set_contact_id(self, contact_id):
        self._contact_id = contact_id

    contact_id = gobject.property(type=object, getter=get_contact_id,
                                  setter=set_contact_id)

    def get_handle(self):
        return self._handle

    def set_handle(self, handle):
        self._handle = handle

    handle = gobject.property(type=object, getter=get_handle,
                              setter=set_handle)
