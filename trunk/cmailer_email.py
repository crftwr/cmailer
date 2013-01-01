import os
#import copy
import fnmatch
#import time
import threading

import email.parser
import mailbox
import poplib

import ckit
from ckit.ckit_const import *

import cmailer_native
import cmailer_misc
import cmailer_mainwindow
#import cfiler_error
import cmailer_debug

## @addtogroup email Email機能
## @{


#--------------------------------------------------------------------

class Account:

    def __init__( self, receiver, sender ):
        self.receiver = receiver
        self.sender = sender

    def receive( self ):
        for email in self.receiver.receive():
            yield email

    def send( self ):
        return self.sender.send()
    
class Receiver:

    def __init__(self):
        pass

    def receive(self):
        pass

class Sender:

    def __init__(self):
        pass

    def send(self):
        pass

class Email( mailbox.mboxMessage ):

    def __init__( self, text ):
    
        msg = email.parser.Parser().parsestr(text)
        mailbox.mboxMessage.__init__( self, msg )

        # Subject
        subject, encoding = email.Header.decode_header(self.get("Subject"))[0]
        if encoding:
            subject = unicode(subject, encoding)
        self.subject = subject
        
        # DateTime
        date = self.get('Date')
        date = email.utils.parsedate(date)
        self.date = date

class Folder( mailbox.mbox ):

    def __init__( self, path ):
        mailbox.mbox.__init__( self, path )

#--------------------------------------------------------------------

class Pop3Receiver( Receiver ):

    def __init__( self, server, port, username, password ):
        self.server = server
        self.port = port
        self.username = username
        self.password = password

    def receive(self):

        pop3 = poplib.POP3_SSL( self.server, self.port )
        pop3.user( self.username )
        pop3.pass_( self.password )
        
        num = len(pop3.list()[1])
        
        for i in xrange(num):
            message = pop3.retr(i+1)
            text = "\n".join(message[1])

            yield Email(text)
        
        pop3.quit()

#--------------------------------------------------------------------

## アイテムのリストアップ機能のベースクラス
class lister_Base:

    def __init__(self):
        pass
    
    def destroy(self):
        pass

    def __call__( self ):
        return []

    def cancel(self):
        pass

    def __unicode__(self):
        return u""
    
    def getLocation(self):
        return u""

    def isLazy(self):
        return True

    def isChanged(self):
        return False

    def getCopy( self, name ):
        return ( lister_Base(), name )

    def getChild( self, name ):
        return lister_Base()

    def getParent(self):
        return ( lister_Base(), "" )

    def getRoot(self):
        return lister_Base()

    def locked(self):
        return False

## アイテムのベースクラス
class item_Base:

    def __init__(self):
        pass

    def __unicode__(self):
        return u""

    def getName(self):
        return u""

    def time(self):
        return (0,0,0,0,0,0)

    def size(self):
        return 0

    def attr(self):
        return 0

    def isdir(self):
        return False

    def ishidden(self):
        return False

    def _select( self, sel=None ):
        pass

    def selected(self):
        return False

    def bookmark(self):
        return False

    def paint( self, window, x, y, width, cursor, itemformat, userdata ):
        pass


# 空のファイルリストを表示する機能
class lister_Empty(lister_Base):

    def __init__(self):
        lister_Base.__init__(self)


# [ - no item - ] を表示するための特別なアイテム
class item_Empty(item_Base):

    def __init__( self, location ):
        self.location = location
        self.name = ""

    def __unicode__(self):
        return os.path.join( self.location, self.name )

    def getName(self):
        return self.name

    def paint( self, window, x, y, width, cursor, itemformat, userdata ):
        if cursor:
            line0=( LINE_BOTTOM, ckit.getColor("file_cursor") )
        else:
            line0=None

        attr = ckit.Attribute( fg=ckit.getColor("error_file_fg"), line0=line0 )

        s = u"- no item -"
        s = ckit.adjustStringWidth(window,s,width,ckit.ALIGN_CENTER)
        window.putString( x, y, width, 1, attr, s )


# ファイルのレンダリング処理
class item_CommonPaint(item_Base):

    def paint( self, window, x, y, width, cursor, itemformat, userdata ):

        if self.isdir():
            if self.ishidden():
                attr_fg=ckit.getColor("hidden_dir_fg")
            else:
                attr_fg=ckit.getColor("dir_fg")
        else:
            if self.ishidden():
                attr_fg=ckit.getColor("hidden_file_fg")
            else:
                attr_fg=ckit.getColor("file_fg")

        if self.selected():
            attr_bg_gradation=( ckit.getColor("select_file_bg1"), ckit.getColor("select_file_bg2"), ckit.getColor("select_file_bg1"), ckit.getColor("select_file_bg2"))
        elif self.bookmark():
            attr_bg_gradation=( ckit.getColor("bookmark_file_bg1"), ckit.getColor("bookmark_file_bg2"), ckit.getColor("bookmark_file_bg1"), ckit.getColor("bookmark_file_bg2"))
        else:
            attr_bg_gradation = None

        if cursor:
            line0=( LINE_BOTTOM, ckit.getColor("file_cursor") )
        else:
            line0=None
        
        attr = ckit.Attribute( fg=attr_fg, bg_gradation=attr_bg_gradation, line0=line0 )

        s = itemformat( window, self, width, userdata )
        window.putString( x, y, width, 1, attr, s )

## 通常のファイルアイテム
#
#  通常の実在するファイルやディレクトリを意味するクラスです。\n\n
#
#  内骨格では、ファイルリストに表示されるアイテムを item_Xxxx という名前のクラスのオブジェクトで表現します。\n
#  
#  @sa item_Zip
#  @sa item_Tar
#  @sa item_Archive
#
class item_Default(item_CommonPaint):

    def __init__( self, location, name, info=None, bookmark=False ):
    
        self.location = location
        self.name = name

        if info==None:
            info_list = cmailer_native.findFile( os.path.join(self.location,self.name) )
            if info_list:
                info = info_list[0]
            else:
                raise IOError( "file does not exist. [%s]" % self.name )

        self._size = info[1]
        self._mtime = info[2]
        self._attr = info[3]

        self._selected = False
        self._bookmark = bookmark

    def __unicode__(self):
        return os.path.join( self.location, self.name )

    def getName(self):
        return self.name

    def getFullpath(self):
        return os.path.join( self.location, self.name )

    def time(self):
        assert( type(self._mtime)==tuple )
        return self._mtime

    def utime( self, time ):
        cmailer_native.setFileTime( os.path.join(self.location,self.name), time )

    def size(self):
        return self._size

    def attr(self):
        return self._attr

    def uattr( self, attr ):
        ckit.setFileAttribute( os.path.join( self.location, self.name ), attr )
        self._attr = attr

    def isdir(self):
        return self._attr & ckit.FILE_ATTRIBUTE_DIRECTORY

    def ishidden(self):
        return self._attr & ckit.FILE_ATTRIBUTE_HIDDEN

    def _select( self, sel=None ):
        if sel==None:
            self._selected = not self._selected
        else:
            self._selected = sel;

    def selected(self):
        return self._selected

    def bookmark(self):
        return self._bookmark

    def lock(self):
        pass

    def walk( self, topdown=True ):

        class packItem:

            def __init__( self, location, dirname ):

                if type(dirname)==type(''):
                    dirname = unicode(dirname,'mbcs')

                self.location = location
                self.dirname = ckit.replacePath(dirname)

            def __call__( self, filename ):

                if type(filename)==type(''):
                    filename = unicode(filename,'mbcs')
                
                try:
                    item = item_Default(
                        self.location,
                        ckit.joinPath( self.dirname, filename )
                        )
                    return item
                except:
                    return None

        fullpath = os.path.join( self.location, self.name )
        for root, dirs, files in os.walk( fullpath, topdown ):
            root = ckit.replacePath(root)
            dirname = root[len(self.location):].lstrip('\\/')
            yield dirname, filter( lambda item:item, map( packItem(self.location,dirname), dirs )), filter( lambda item:item, map( packItem(self.location,dirname), files ))

    def delete( self, recursive, item_filter, schedule_handler, log_writer=None ):

        if not log_writer:
            def logWriter(s) : pass
            log_writer = logWriter

        def remove_file( filename ):
            log_writer( u'ファイル削除 : %s …' % filename )
            try:
                # READONLY属性を落とさないと削除できない
                attr = ckit.getFileAttribute(filename)
                if attr & ckit.FILE_ATTRIBUTE_READONLY:
                    attr &= ~ckit.FILE_ATTRIBUTE_READONLY
                    ckit.setFileAttribute(filename,attr)
                # 削除
                os.unlink(filename)
            except Exception, e:
                log_writer( u'失敗\n' )
                log_writer( "  %s\n" % unicode(str(e),'mbcs') )
                cmailer_debug.printErrorInfo()
            else:
                log_writer( u'完了\n' )

        def remove_dir( filename ):
            log_writer( u'ディレクトリ削除 : %s …' % filename )

            if len(os.listdir(filename))>0:
                log_writer( u'空ではない\n' )
                return

            try:
                # READONLY属性を落とさないと削除できない
                attr = ckit.getFileAttribute(filename)
                if attr & ckit.FILE_ATTRIBUTE_READONLY:
                    attr &= ~ckit.FILE_ATTRIBUTE_READONLY
                    ckit.setFileAttribute(filename,attr)
                # 削除
                os.rmdir(filename)
            except Exception, e:
                log_writer( u'失敗\n' )
                log_writer( "  %s\n" % unicode(str(e),'mbcs') )
                cmailer_debug.printErrorInfo()
            else:
                log_writer( u'完了\n' )

        fullpath = ckit.joinPath( self.location, self.name )
        if self.isdir():
            if recursive:
                for root, dirs, files in os.walk( fullpath, False ):
                    if schedule_handler(): return
                    root = ckit.replacePath(root)
                    for name in files:
                        if schedule_handler(): return
                        if item_filter==None or item_filter( item_Default(root,name) ):
                            remove_file( ckit.joinPath(root, name) )
                    if schedule_handler(): return
                    remove_dir(root)
            else:
                remove_dir(fullpath)
        else:
            remove_file(fullpath)

    def open(self):
        return file( os.path.join( self.location, self.name ), "rb" )

    def rename( self, name ):
        src = os.path.join(self.location,self.name)
        dst = os.path.join(self.location,name)
        os.rename( src, dst )
        self.name = name

    def getLink(self):
        if not self.isdir():
            ext = os.path.splitext(self.name)[1].lower()
            if ext in (".lnk",".pif"):
                program, param, directory, swmode = cmailer_native.getShellLinkInfo(self.getFullpath())
                link = item_Default(
                    self.location,
                    program
                    )
                return link
        return None            


# ローカルファイルシステム上のリスト機能
class lister_LocalFS(lister_Base):

    def __init__( self, main_window, location ):
        if type(location)==type(''):
            location = unicode(location,'mbcs')
        self.main_window = main_window
        self.location = ckit.normPath(location)

    def getLocation(self):
        return self.location

    def locked(self):
        return False

    def exists( self, name ):
        fullpath = os.path.join( self.location, name )
        if os.path.exists( os.path.join( self.location, name ) ):
            item = item_Default(
                self.location,
                name
                )
            return item
        return None

    def mkdir( self, name, log_writer=None ):

        if not log_writer:
            def logWriter(s) : pass
            log_writer = logWriter

        fullpath = ckit.joinPath( self.location, name )
        log_writer( u'ディレクトリ作成 : %s …' % fullpath )
        if os.path.exists(fullpath) and os.path.isdir(fullpath):
            log_writer( u'すでに存在\n' )
            return
        try:
            os.makedirs(fullpath)
        except Exception, e:
            log_writer( u'失敗\n' )
            log_writer( "  %s\n" % unicode(str(e),'mbcs') )
            cmailer_debug.printErrorInfo()
        else:
            log_writer( u'完了\n' )

    def getCopyDst( self, name ):

        fullpath = os.path.join( self.location, name )

        try:
            dirname = os.path.split(fullpath)[0]
            os.makedirs(dirname)
        except:
            pass

        # READONLY属性を落とさないと上書きできない
        attr = ckit.getFileAttribute(fullpath)
        if attr & ckit.FILE_ATTRIBUTE_READONLY:
            attr &= ~ckit.FILE_ATTRIBUTE_READONLY
            ckit.setFileAttribute(fullpath,attr)

        return file( fullpath, "wb" )

    def getRoot(self):
        dirname = self.location
        root = ckit.rootPath( self.location )
        return lister_Default(self.main_window,root)


# 標準的なディレクトリのリストアップ機能
class lister_Default(lister_LocalFS):

    def __init__( self, main_window, location ):
        lister_LocalFS.__init__( self, main_window, location )
        
    def destroy(self):
        lister_LocalFS.destroy(self)

    def __call__( self ):

        def packListItem( fileinfo ):

            item = item_Default(
                self.location,
                fileinfo[0],
                fileinfo,
                bookmark = False
                )

            return item

        #bookmark_items = self.main_window.bookmark.listDir(self.location)

        cmailer_misc.checkNetConnection(self.location)

        fileinfo_list = cmailer_native.findFile( os.path.join(self.location,"*") )
        items = map( packListItem, fileinfo_list )

        return items

    def cancel(self):
        pass

    def __unicode__(self):
        return self.location

    def isLazy(self):
        return False

    def isChanged(self):
        return False

    def getCopy( self, name ):
        return ( lister_Default( self.main_window, self.location ), name )

    def getChild( self, name ):
        return lister_Default( self.main_window, os.path.join( self.location, name ) )

    def getParent(self):
        parent, name = ckit.splitPath( self.location )
        if not name:
            raise cfiler_error.NotExistError
        return ( lister_Default(self.main_window,parent), name )

    def touch( self, name ):

        fullpath = os.path.join( self.location, name )

        if not os.path.exists(fullpath):
            fd = file( fullpath, "wb" )
            del fd

        item = item_Default(
            self.location,
            name
            )
        return item

    def unlink( self, name ):
        fullpath = os.path.join( self.location, name )

        # READONLY属性を落とさないと削除できない
        attr = ckit.getFileAttribute(fullpath)
        if attr & ckit.FILE_ATTRIBUTE_READONLY:
            attr &= ~ckit.FILE_ATTRIBUTE_READONLY
            ckit.setFileAttribute(fullpath,attr)

        os.unlink( fullpath )

    def canRenameFrom( self, other ):
        if not isinstance( other, lister_Default ) : return False
        return os.path.splitdrive(self.location)[0].lower()==os.path.splitdrive(other.location)[0].lower()

    def rename( self, src_item, dst_name ):
        dst_fullpath = os.path.join( self.location, dst_name )
        os.rename( src_item.getFullpath(), dst_fullpath )

    def popupContextMenu( self, window, x, y, items=None ):
        if items==None:
            directory, name = ckit.splitPath(os.path.normpath(self.location))
            if name:
                return cmailer_native.popupContextMenu( window.getHWND(), x, y, directory, [name] )
            else:
                return cmailer_native.popupContextMenu( window.getHWND(), x, y, "", [directory] )
        else:
            filename_list = map( lambda item : os.path.normpath(item.getName()), items )
            return cmailer_native.popupContextMenu( window.getHWND(), x, y, os.path.normpath(self.location), filename_list )


# 外部からアイテムリストを受け取る機能
class lister_Custom(lister_LocalFS):

    def __init__( self, main_window, prefix, location, items ):
        lister_LocalFS.__init__(self,main_window,location)
        self.prefix = prefix
        self.items = items

    def destroy(self):
        lister_LocalFS.destroy(self)

    def __call__( self ):
        items = []
        for item in self.items:
            items.append( copy.copy(item) )
        return items

    def cancel(self):
        pass

    def __unicode__(self):
        return self.prefix + self.location

    def isLazy(self):
        return True

    def isChanged(self):
        return False

    def getCopy( self, name ):
        path = ckit.joinPath( self.location, name )
        dirname, filename = ckit.splitPath(path)
        return ( lister_Default( self.main_window, dirname ), filename )

    def getChild( self, name ):
        return lister_Default( self.main_window, os.path.join( self.location, name ) )

    def getParent(self):
        return ( lister_Default(self.main_window,self.location), "" )

#--------------------------------------------------------------------

## 標準的なアイテムの表示形式
def itemformat_Name_Ext_Size_YYMMDD_HHMMSS( window, item, width, userdata ):

    if item.isdir():
        str_size = "<DIR>"
    else:
        str_size = "%6s" % cmailer_misc.getFileSizeString(item.size())

    t = item.time()
    str_time = "%02d/%02d/%02d %02d:%02d:%02d" % ( t[0]%100, t[1], t[2], t[3], t[4], t[5] )

    str_size_time = "%s %s" % ( str_size, str_time )

    width = max(40,width)
    filename_width = width-len(str_size_time)

    if item.isdir():
        body, ext = item.name, None
    else:
        body, ext = ckit.splitExt(item.name)

    if ext:
        body_width = min(width,filename_width-6)
        return ( ckit.adjustStringWidth(window,body,body_width,ckit.ALIGN_LEFT,ckit.ELLIPSIS_RIGHT)
               + ckit.adjustStringWidth(window,ext,6,ckit.ALIGN_LEFT,ckit.ELLIPSIS_NONE)
               + str_size_time )
    else:
        return ( ckit.adjustStringWidth(window,body,filename_width,ckit.ALIGN_LEFT,ckit.ELLIPSIS_RIGHT)
               + str_size_time )

## 秒を省いたアイテムの表示形式
def itemformat_Name_Ext_Size_YYMMDD_HHMM( window, item, width, userdata ):

    if item.isdir():
        str_size = "<DIR>"
    else:
        str_size = "%6s" % cmailer_misc.getFileSizeString(item.size())

    t = item.time()
    str_time = "%02d/%02d/%02d %02d:%02d" % ( t[0]%100, t[1], t[2], t[3], t[4] )

    str_size_time = "%s %s" % ( str_size, str_time )

    width = max(40,width)
    filename_width = width-len(str_size_time)

    if item.isdir():
        body, ext = item.name, None
    else:
        body, ext = ckit.splitExt(item.name)

    if ext:
        body_width = min(width,filename_width-6)
        return ( ckit.adjustStringWidth(window,body,body_width,ckit.ALIGN_LEFT,ckit.ELLIPSIS_RIGHT)
               + ckit.adjustStringWidth(window,ext,6,ckit.ALIGN_LEFT,ckit.ELLIPSIS_NONE)
               + str_size_time )
    else:
        return ( ckit.adjustStringWidth(window,body,filename_width,ckit.ALIGN_LEFT,ckit.ELLIPSIS_RIGHT)
               + str_size_time )

## ファイル名だけを表示するアイテムの表示形式
def itemformat_NameExt( window, item, width, userdata ):
    return ckit.adjustStringWidth(window,item.name,width,ckit.ALIGN_LEFT,ckit.ELLIPSIS_RIGHT)


#--------------------------------------------------------------------

## ワイルドカードを使ったフィルタ機能
#
#  ワイルドカードを使った標準的なフィルタ機能です。\n\n
#
#  内骨格では、フィルタと呼ばれるオブジェクトを使って、ファイルリストのアイテムを絞り込んで表示することが出来ます。\n
#  フィルタは filter_Xxxx という名前のクラスのオブジェクトで表現します。\n
#  
#  @sa filter_Bookmark
#
class filter_Default:

    def __init__( self, pattern="*", dir_policy=True ):
        self.pattern = pattern
        self.pattern_list = pattern.split()
        self.dir_policy = dir_policy

    def __call__( self, item ):

        if self.dir_policy!=None and item.isdir() : return self.dir_policy

        for pattern in self.pattern_list:
            if fnmatch.fnmatch( item.name, pattern ) : return True
        return False

    def __unicode__(self):
        if self.pattern=='*' : return u""
        return self.pattern

    def canRenameDir(self):
        return (self.pattern=="*")

## ブックマークを使ったフィルタ機能
#
#  ブックマークに登録されているアイテムのみを表示するためのフィルタ機能です。\n\n
#
#  内骨格では、フィルタと呼ばれるオブジェクトを使って、ファイルリストのアイテムを絞り込んで表示することが出来ます。\n
#  フィルタは filter_Xxxx という名前のクラスのオブジェクトで表現します。\n
#  
#  @sa filter_Default
#
class filter_Bookmark:

    def __init__( self, dir_policy=True ):
        self.dir_policy = dir_policy

    def __call__( self, item ):
        if self.dir_policy!=None and item.isdir() : return self.dir_policy
        return item.bookmark()

    def __unicode__(self):
        return u"[bookmark]"

#--------------------------------------------------------------------

## ファイルの名前を使ってソートする機能
#
#  ファイル名を使ってアイテムをソートするための機能です。\n\n
#
#  内骨格では、ソータと呼ばれるオブジェクトを使って、ファイルリストのアイテムを並べ替えて表示することが出来ます。\n
#  ソータは sorter_Xxxx という名前のクラスのオブジェクトで表現します。\n
#  
#  @sa sorter_ByExt
#  @sa sorter_BySize
#  @sa sorter_ByTimeStamp
#
class sorter_ByName:

    ## コンストラクタ
    #  @param self  -
    #  @param order 並びの順序。1=昇順、-1=降順
    def __init__( self, order=1 ):
        self.order = order

    def __call__( self, left, right ):
        if left.isdir() and not right.isdir() :
            return -1
        elif not left.isdir() and right.isdir() :
            return 1
        return cmp( left.name.lower(), right.name.lower() ) * self.order

## ファイルの拡張子を使ってソートする機能
#
#  ファイルの拡張子を使ってアイテムをソートするための機能です。\n\n
#
#  内骨格では、ソータと呼ばれるオブジェクトを使って、ファイルリストのアイテムを並べ替えて表示することが出来ます。\n
#  ソータは sorter_Xxxx という名前のクラスのオブジェクトで表現します。\n
#  
#  @sa sorter_ByName
#  @sa sorter_BySize
#  @sa sorter_ByTimeStamp
#
class sorter_ByExt:

    ## コンストラクタ
    #  @param self  -
    #  @param order 並びの順序。1=昇順、-1=降順
    def __init__( self, order=1 ):
        self.order = order

    def __call__( self, left, right ):
        if left.isdir() and not right.isdir() :
            return -1
        elif not left.isdir() and right.isdir() :
            return 1
        cmp_result_ext = cmp( os.path.splitext(left.name)[1].lower(), os.path.splitext(right.name)[1].lower() )
        if cmp_result_ext : return cmp_result_ext * self.order
        return cmp( left.name.lower(), right.name.lower() ) * self.order

## ファイルのサイズを使ってソートする機能
#
#  ファイルのサイズを使ってアイテムをソートするための機能です。\n\n
#
#  内骨格では、ソータと呼ばれるオブジェクトを使って、ファイルリストのアイテムを並べ替えて表示することが出来ます。\n
#  ソータは sorter_Xxxx という名前のクラスのオブジェクトで表現します。\n
#  
#  @sa sorter_ByName
#  @sa sorter_ByExt
#  @sa sorter_ByTimeStamp
#
class sorter_BySize:

    ## コンストラクタ
    #  @param self  -
    #  @param order 並びの順序。1=昇順、-1=降順
    def __init__( self, order=1 ):
        self.order = order

    def __call__( self, left, right ):
        if left.isdir() and not right.isdir() :
            return -1
        elif not left.isdir() and right.isdir() :
            return 1
        return cmp( left.size(), right.size() ) * self.order

## ファイルのタイムスタンプを使ってソートする機能
#
#  ファイルのタイムスタンプを使ってアイテムをソートするための機能です。\n\n
#
#  内骨格では、ソータと呼ばれるオブジェクトを使って、ファイルリストのアイテムを並べ替えて表示することが出来ます。\n
#  ソータは sorter_Xxxx という名前のクラスのオブジェクトで表現します。\n
#  
#  @sa sorter_ByName
#  @sa sorter_ByExt
#  @sa sorter_BySize
#
class sorter_ByTimeStamp:

    ## コンストラクタ
    #  @param self  -
    #  @param order 並びの順序。1=昇順、-1=降順
    def __init__( self, order=1 ):
        self.order = order

    def __call__( self, left, right ):
        if left.isdir() and not right.isdir() :
            return -1
        elif not left.isdir() and right.isdir() :
            return 1
        return cmp( left.time(), right.time() ) * self.order

#--------------------------------------------------------------------

## ファイルリスト
#
#  ファイルアイテムの列挙、フィルタリング、ソート、という一連の操作を実行し、アイテムのリストを管理するクラスです。\n
#  MainWindow.activeFileList() などで取得されるのが FileList オブジェクトです。
#
class FileList:

    def __init__( self, main_window, lister, item_filter=filter_Default( "*", dir_policy=True ), sorter=sorter_ByName() ):

        self.main_window = main_window

        self.lister = lister
        self.item_filter = item_filter
        self.sorter = sorter
        self.disk_size_info = None
        self.disk_size_string = u""
        self.job_queue = ckit.JobQueue()
        self.job_item = None
        self.lock = threading.RLock()

        self.original_items = [] # 作成中のアイテムリスト(列挙直後)
        self.back_items = []     # 作成中のアイテムリスト(フィルタ/ソート適用後)
        self.items = []          # 完成済みのアイテムリスト
        self.applyItems()

    def destroy(self):
        self.lister.destroy()
        self.job_queue.cancel()
        self.job_queue.join()
        self.job_queue.destroy()

    def __unicode__(self):
        return u" %s %s " % ( self.lister, self.item_filter )

    def _callLister( self, manual, keep_selection=False ):

        if not manual and self.lister.isLazy() : return

        if keep_selection:
            old_items = dict( map( lambda item : [ item.name, item ], self.original_items ) )

        self.main_window.setStatusMessage( u"List ..." )
        try:
            self.original_items = self.lister()
        finally:
            self.main_window.clearStatusMessage()

        if keep_selection:
            for item in self.original_items:
                try:
                    if old_items[item.name].selected():
                        item._select(True)
                except KeyError:
                    continue

        self.delayedUpdateInfo()

    def _callFilterAndSorter(self):

        if self.item_filter:
            self.back_items = filter( self.item_filter, self.original_items )
        else:
            self.back_items = self.original_items[:]

        if not self.main_window.isHiddenFileVisible():
            def isNotHidden(item):
                return not item.ishidden()
            self.back_items = filter( isNotHidden, self.back_items )

        if self.sorter:
            self.back_items.sort( self.sorter )

    def delayedUpdateInfo(self):

        def jobUpdateInfo(job_item):
            self.lock.acquire()
            try:
                self.disk_size_info = ckit.getDiskSize( os.path.splitdrive(self.getLocation())[0] )
            finally:
                self.lock.release()

        def jobUpdateInfoFinished(job_item):
            if job_item.isCanceled() : return
            self.main_window.paint(cmailer_mainwindow.PAINT_LEFT_FOOTER)

        self.lock.acquire()
        try:
            self.disk_size_info = None
            if self.job_item:
                self.job_item.cancel()
                self.job_item = None
            self.job_item = ckit.JobItem( jobUpdateInfo, jobUpdateInfoFinished )
            self.job_queue.enqueue(self.job_item)
        finally:
            self.lock.release()

    def _updateInfo(self):

        self.num_file = 0
        self.num_dir = 0
        self.num_file_selected = 0
        self.num_dir_selected = 0
        self.selected_size = 0

        for item in self.items:
            isdir = item.isdir()
            if isdir:
                self.num_dir += 1
                if item.selected():
                    self.num_dir_selected += 1
            else:
                self.num_file += 1
                if item.selected():
                    self.num_file_selected += 1
                    self.selected_size += item.size()

    def selectItem( self, i, sel=None ):

        item = self.items[i]
        sel_prev = self.items[i].selected()
        item._select(sel)

        if item.selected() != sel_prev:
            if item.selected():
                if item.isdir():
                    self.num_dir_selected += 1
                else:
                    self.num_file_selected += 1
                    self.selected_size += item.size()
            else:
                if item.isdir():
                    self.num_dir_selected -= 1
                else:
                    self.num_file_selected -= 1
                    self.selected_size -= item.size()

    def isChanged(self):
        return self.lister.isChanged()

    def refresh( self, manual=False, keep_selection=False ):
        self._callLister(manual,keep_selection)
        self._callFilterAndSorter()

    def setLister( self, lister ):
        old_lister = self.lister
        self.lister = lister
        try:
            self._callLister(True)
            self._callFilterAndSorter()
        except:
            self.lister.destroy()
            self.lister = old_lister
            raise
        old_lister.destroy()    
        del old_lister

    def getLister(self):
        return self.lister

    def getLocation(self):
        return self.lister.getLocation()

    def setFilter( self, new_filter ):
        self.item_filter = new_filter
        self._callFilterAndSorter()

    def getFilter(self):
        return self.item_filter

    def setSorter( self, new_sorter ):
        self.sorter = new_sorter
        self._callFilterAndSorter()

    def getSorter(self):
        return self.sorter

    def applyItems(self):

        self.items = self.back_items

        if len(self.items)==0:
            self.items.append( item_Empty(unicode(self.lister)) )

        self._updateInfo()

    def getHeaderInfo(self):

        if self.num_dir_selected==0 and self.num_file_selected==0 : return u""

        if self.num_dir_selected==0:
            str_dir = u""
        elif self.num_dir_selected==1:
            str_dir = "%d Dir " % self.num_dir_selected
        else:
            str_dir = "%d Dirs " % self.num_dir_selected

        if self.num_file_selected==0:
            str_file = u""
        elif self.num_file_selected==1:
            str_file = "%d File " % self.num_file_selected
        else:
            str_file = "%d Files " % self.num_file_selected

        if self.selected_size==0:
            str_size = u""
        else:
            str_size = cmailer_misc.getFileSizeString( self.selected_size ) + u" "

        return u"%s%s%sMarked" % ( str_dir, str_file, str_size )

    def getFooterInfo(self):

        self.lock.acquire()
        try:
            if self.disk_size_info:
                if self.num_dir<=1:
                    str_dir = "%d Dir" % self.num_dir
                else:
                    str_dir = "%d Dirs" % self.num_dir

                if self.num_file<=1:
                    str_file = "%d File" % self.num_file
                else:
                    str_file = "%d Files" % self.num_file

                self.disk_size_string = u"%s  %s  %s (%s)" % ( str_dir, str_file, cmailer_misc.getFileSizeString(self.disk_size_info[1]), cmailer_misc.getFileSizeString(self.disk_size_info[0]) )

            return self.disk_size_string

        finally:
            self.lock.release()

    def numItems(self):
        return len(self.items)

    def getItem(self,index):
        return self.items[index]

    def indexOf(self,filename):
        for i in xrange(len(self.items)):
            if self.items[i].name == filename:
                return i
        return -1

    def selected(self):
        for item in self.items:
            if item.selected():
                return True
        return False

## @} email

