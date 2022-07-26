# Copyright (c) 2022 Daniel Pereira
# Copyright (c) 2016 Chris Billington
#
# SPDX-License-Identifier: Apache-2.0 AND BSD-2-Clause

# This small inotify library is based on the excellent `inotify_simple` available at
# `chrisjbillington/inotify_simple` on Github, commit: 5573789 at Jun 20, 2022.
#
# In general, I removed support for past Python versions and removed support for an IO selector,
# so that if you want such feature you need to do it externally. In short, this is even simpler than
# what the original lib proposed.
#
# See: https://github.com/chrisjbillington/inotify_simple

from os import fsencode, fsdecode, read, strerror, O_CLOEXEC, O_NONBLOCK
from enum import Enum, IntEnum
from collections import namedtuple
from struct import unpack_from, calcsize
from ctypes import CDLL, get_errno, c_int
from ctypes.util import find_library
from errno import EINTR
from termios import FIONREAD
from fcntl import ioctl
from io import FileIO

_libc = None

def _libc_call(function, *args):
    """Wrapper which raises errors and retries on EINTR."""
    while True:
        rc = function(*args)
        if rc != -1:
            return rc
        errno = get_errno()
        if errno != EINTR:
            raise OSError(errno, strerror(errno))


#: A ``namedtuple`` (wd, mask, cookie, name) for an inotify event. The
#: :attr:`~inotify_simple.Event.name` field is a ``str`` decoded with
#: ``os.fsdecode()``
Event = namedtuple('Event', ['wd', 'mask', 'cookie', 'name'])

_EVENT_FMT = 'iIII'
_EVENT_SIZE = calcsize(_EVENT_FMT)


class INotify(FileIO):
    """
    This is a simple FileIO wrapper around OS native inotify system calls.

    Attempting to read from `INotify.fileno()` using `os.read()` will ocasionally raise a
    ``BlockingIOError`` if there's no data available to read from.
    """

    #: The inotify file descriptor returned by ``inotify_init()``. You are
    #: free to use it directly with ``os.read`` if you'd prefer not to call
    #: :func:`~inotify_simple.INotify.read` for some reason. Also available as
    #: :func:`~inotify_simple.INotify.fileno`
    fd = property(FileIO.fileno)

    def __init__(self, inheritable=False):
        """File-like object wrapping ``inotify_init1()``. Raises ``OSError`` on failure.
        :func:`~inotify_simple.INotify.close` should be called when no longer needed.
        Can be used as a context manager to ensure it is closed, and can be used
        directly by functions expecting a file-like object, such as ``select``, or with
        functions expecting a file descriptor via
        :func:`~inotify_simple.INotify.fileno`.

        Args:
            inheritable (bool): whether the inotify file descriptor will be inherited by
                child processes. The default,``False``, corresponds to passing the
                ``IN_CLOEXEC`` flag to ``inotify_init1()``. Setting this flag when
                opening filedescriptors is the default behaviour of Python standard
                library functions since PEP 446.

            nonblocking (bool): whether to open the inotify file descriptor in
                nonblocking mode, corresponding to passing the ``IN_NONBLOCK`` flag to
                ``inotify_init1()``. This does not affect the normal behaviour of
                :func:`~inotify_simple.INotify.read`, which uses ``poll()`` to control
                blocking behaviour according to the given timeout, but will cause other
                reads of the file descriptor (for example if the application reads data
                manually with ``os.read(fd)``) to raise ``BlockingIOError`` if no data
                is available."""
        try:
            libc_so = find_library('c')
        except RuntimeError: # Python on Synology NASs raises a RuntimeError
            libc_so = None
        global _libc; _libc = _libc or CDLL(libc_so or 'libc.so.6', use_errno=True)
        flags = (not inheritable) * O_CLOEXEC
        FileIO.__init__(self, _libc_call(_libc.inotify_init1, flags), mode='rb')

    def add_watch(self, path, mask):
        """Wrapper around ``inotify_add_watch()``. Returns the watch
        descriptor or raises an ``OSError`` on failure.

        Args:
            path (str, bytes, or PathLike): The path to watch. Will be encoded with
                ``os.fsencode()`` before being passed to ``inotify_add_watch()``.

            mask (int): The mask of events to watch for. Can be constructed by
                bitwise-ORing :class:`~inotify_simple.flags` together.

        Returns:
            int: watch descriptor"""
        return _libc_call(_libc.inotify_add_watch, self.fileno(), fsencode(path), mask)

    def rm_watch(self, wd):
        """Wrapper around ``inotify_rm_watch()``. Raises ``OSError`` on failure.

        Args:
            wd (int): The watch descriptor to remove"""
        _libc_call(_libc.inotify_rm_watch, self.fileno(), wd)

    def read(self):
        """Read the inotify file descriptor and return the resulting
        :attr:`~inotify_simple.Event` namedtuples (wd, mask, cookie, name).

        It might return an empty list if nothing is available for reading at the time, as this is a
        non-blocking read. Use a `selector` if you need to know when there's data to read from.

        Returns:
            list: list of :attr:`~inotify_simple.Event` namedtuples"""
        data = self._readbytes()
        if not data:
            return []
        return parse_events(data)

    def _readbytes(self):
        bytes_avail = c_int()
        ioctl(self.fileno(), FIONREAD, bytes_avail)
        if not bytes_avail.value:
            return b''
        return read(self.fileno(), bytes_avail.value)


def parse_events(data):
    """Unpack data read from an inotify file descriptor into
    :attr:`~inotify_simple.Event` namedtuples (wd, mask, cookie, name). This function
    can be used if the application has read raw data from the inotify file
    descriptor rather than calling :func:`~inotify_simple.INotify.read`.

    Args:
        data (bytes): A bytestring as read from an inotify file descriptor.

    Returns:
        list: list of :attr:`~inotify_simple.Event` namedtuples"""
    pos = 0
    events = []
    while pos < len(data):
        wd, mask, cookie, namesize = unpack_from(_EVENT_FMT, data, pos)
        pos += _EVENT_SIZE + namesize
        name = data[pos - namesize : pos].split(b'\x00', 1)[0]
        events.append(Event(wd, mask, cookie, fsdecode(name)))
    return events


class flags(IntEnum):
    """Inotify flags as defined in ``inotify.h`` but with ``IN_`` prefix omitted.
    Includes a convenience method :func:`~inotify_simple.flags.from_mask` for extracting
    flags from a mask."""
    ACCESS = 0x00000001  #: File was accessed
    MODIFY = 0x00000002  #: File was modified
    ATTRIB = 0x00000004  #: Metadata changed
    CLOSE_WRITE = 0x00000008  #: Writable file was closed
    CLOSE_NOWRITE = 0x00000010  #: Unwritable file closed
    OPEN = 0x00000020  #: File was opened
    MOVED_FROM = 0x00000040  #: File was moved from X
    MOVED_TO = 0x00000080  #: File was moved to Y
    CREATE = 0x00000100  #: Subfile was created
    DELETE = 0x00000200  #: Subfile was deleted
    DELETE_SELF = 0x00000400  #: Self was deleted
    MOVE_SELF = 0x00000800  #: Self was moved

    UNMOUNT = 0x00002000  #: Backing fs was unmounted
    Q_OVERFLOW = 0x00004000  #: Event queue overflowed
    IGNORED = 0x00008000  #: File was ignored

    ONLYDIR = 0x01000000  #: only watch the path if it is a directory
    DONT_FOLLOW = 0x02000000  #: don't follow a sym link
    EXCL_UNLINK = 0x04000000  #: exclude events on unlinked objects
    MASK_ADD = 0x20000000  #: add to the mask of an already existing watch
    ISDIR = 0x40000000  #: event occurred against dir
    ONESHOT = 0x80000000  #: only send event once

    @classmethod
    def from_mask(cls, mask):
        """Convenience method that returns a list of every flag in a mask."""
        return [flag for flag in cls.__members__.values() if flag & mask]


class masks(IntEnum):
    """Convenience masks as defined in ``inotify.h`` but with ``IN_`` prefix omitted."""
    #: helper event mask equal to ``flags.CLOSE_WRITE | flags.CLOSE_NOWRITE``
    CLOSE = flags.CLOSE_WRITE | flags.CLOSE_NOWRITE
    #: helper event mask equal to ``flags.MOVED_FROM | flags.MOVED_TO``
    MOVE = flags.MOVED_FROM | flags.MOVED_TO

    #: bitwise-OR of all the events that can be passed to
    #: :func:`~inotify_simple.INotify.add_watch`
    ALL_EVENTS  = (flags.ACCESS | flags.MODIFY | flags.ATTRIB | flags.CLOSE_WRITE |
        flags.CLOSE_NOWRITE | flags.OPEN | flags.MOVED_FROM | flags.MOVED_TO |
        flags.CREATE | flags.DELETE| flags.DELETE_SELF | flags.MOVE_SELF)
