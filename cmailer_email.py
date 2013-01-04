import os
#import copy
import fnmatch
import threading
import StringIO

import email.parser
import mailbox
import poplib

import ckit
from ckit.ckit_const import *

import cmailer_native
import cmailer_misc
import cmailer_mainwindow
import cmailer_debug

## @addtogroup email Email機能
## @{

#--------------------------------------------------------------------

class Account:

    def __init__( self, ini, receiver, sender ):
        self.ini = ini
        self.receiver = receiver
        self.sender = sender

    def receive( self ):
        for email in self.receiver.receive( self.ini ):
            yield email

    def send( self ):
        return self.sender.send()
    
class Receiver:

    def __init__(self):
        pass

    def receive( self, ini ):
        pass

class Sender:

    def __init__(self):
        pass

    def send( self, ini ):
        pass

class Email( mailbox.mboxMessage ):

    def __init__( self, message ):
    
        mailbox.mboxMessage.__init__( self, message )

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
    
    def __iter__(self):
        for message in mailbox.mbox.__iter__(self):
            yield Email(message)

#--------------------------------------------------------------------

class Pop3Receiver( Receiver ):

    def __init__( self, server, port, username, password ):
        self.server = server
        self.port = port
        self.username = username
        self.password = password

    def pop3(self):
        return poplib.POP3( self.server, self.port )

    def receive( self, ini ):

        pop3 = self.pop3()
        pop3.user( self.username )
        pop3.pass_( self.password )
        
        lastid = ini.getint( "ACCOUNT", "lastid" )
        
        pop3_list = pop3.list()[1]
        print pop3_list
        
        for i in xrange( len(pop3_list) ):

            message_id, message_len = pop3_list[i].split(" ")
            
            if int(message_id) <= lastid:
                print "Skip:", pop3_list[i]
                continue

            message = pop3.retr(i+1)
            text = "\n".join(message[1])
            msg = email.parser.Parser().parsestr(text)
            yield Email(msg)

        ini.set( "ACCOUNT", "lastid", message_id )
        pop3.quit()

class Pop3SslReceiver( Pop3Receiver ):

    def pop3(self):
        return poplib.POP3_SSL( self.server, self.port )

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

    def select( self, sel=None ):
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


## Emailアイテム
#
#  Emailの１通のメッセージを意味するクラスです。\n\n
#
#  CraftMailerでは、ファイルリストに表示されるアイテムを item_Xxxx という名前のクラスのオブジェクトで表現します。\n
#  
class item_Email(item_Base):

    def __init__( self, folder, key, message ):
    
        self.folder = folder
        self.key = key
        self.message = message
        
        self.name = message.subject
        self._size = len(message.as_string()) # FIXME : パフォーマンス要チェック
        self._mtime = message.date

        self._selected = False

    def __unicode__(self):
        return os.path.join( self.location, self.name )

    def getName(self):
        return self.name

    def time(self):
        assert( type(self._mtime)==tuple )
        return self._mtime

    def size(self):
        return self._size

    def select( self, sel=None ):
        if sel==None:
            self._selected = not self._selected
        else:
            self._selected = sel;

    def selected(self):
        return self._selected

    def bookmark(self):
        return False

    def paint( self, window, x, y, width, cursor, itemformat, userdata ):

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

    def openBody(self):
        if self.message.is_multipart():
            s = self.message.get_payload(0,decode=True)
            print s
        else:
            s = self.message.get_payload(decode=True)
            print s
            
        if s==None: s = u"ABC\nDEF\nGHI"
        fd = StringIO.StringIO(s)
        return fd

    def delete( self, used_folder_set, schedule_handler, log_writer=None ):

        if not log_writer:
            def logWriter(s) : pass
            log_writer = logWriter

        used_folder_set.add(self.folder)

        log_writer( u'削除 : %s …' % self.name )
        self.folder.remove(self.key)
        log_writer( u'完了\n' )


# 汎用のメールのリスト機能
class lister_Folder(lister_Base):

    def __init__( self, folder ):
        self.folder = folder

    def destroy(self):
        lister_Base.destroy(self)

    def getLocation(self):
        return u"mail"

    def __call__( self ):
        items = []
        for key, message in self.folder.iteritems():
            items.append( item_Email( self.folder, key, Email( message ) ) )
        return items

    def cancel(self):
        pass

    def __unicode__(self):
        return u"mail"

    def isLazy(self):
        return False


#--------------------------------------------------------------------

## 標準的なアイテムの表示形式
def itemformat_Name_Ext_Size_YYMMDD_HHMMSS( window, item, width, userdata ):

    str_size = "%6s" % cmailer_misc.getFileSizeString(item.size())

    t = item.time()
    str_time = "%02d/%02d/%02d %02d:%02d:%02d" % ( t[0]%100, t[1], t[2], t[3], t[4], t[5] )

    str_size_time = "%s %s" % ( str_size, str_time )

    width = max(40,width)
    filename_width = width-len(str_size_time)

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

    str_size = "%6s" % cmailer_misc.getFileSizeString(item.size())

    t = item.time()
    str_time = "%02d/%02d/%02d %02d:%02d" % ( t[0]%100, t[1], t[2], t[3], t[4] )

    str_size_time = "%s %s" % ( str_size, str_time )

    width = max(40,width)
    filename_width = width-len(str_size_time)

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
#  CraftMailerでは、フィルタと呼ばれるオブジェクトを使って、ファイルリストのアイテムを絞り込んで表示することが出来ます。\n
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

        if self.dir_policy!=None : return self.dir_policy

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
#  CraftMailerでは、フィルタと呼ばれるオブジェクトを使って、ファイルリストのアイテムを絞り込んで表示することが出来ます。\n
#  フィルタは filter_Xxxx という名前のクラスのオブジェクトで表現します。\n
#  
#  @sa filter_Default
#
class filter_Bookmark:

    def __init__( self, dir_policy=True ):
        self.dir_policy = dir_policy

    def __call__( self, item ):
        if self.dir_policy!=None : return self.dir_policy
        return item.bookmark()

    def __unicode__(self):
        return u"[bookmark]"

#--------------------------------------------------------------------

## ファイルの名前を使ってソートする機能
#
#  ファイル名を使ってアイテムをソートするための機能です。\n\n
#
#  CraftMailerでは、ソータと呼ばれるオブジェクトを使って、ファイルリストのアイテムを並べ替えて表示することが出来ます。\n
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
        return cmp( left.name.lower(), right.name.lower() ) * self.order

## ファイルの拡張子を使ってソートする機能
#
#  ファイルの拡張子を使ってアイテムをソートするための機能です。\n\n
#
#  CraftMailerでは、ソータと呼ばれるオブジェクトを使って、ファイルリストのアイテムを並べ替えて表示することが出来ます。\n
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
        cmp_result_ext = cmp( os.path.splitext(left.name)[1].lower(), os.path.splitext(right.name)[1].lower() )
        if cmp_result_ext : return cmp_result_ext * self.order
        return cmp( left.name.lower(), right.name.lower() ) * self.order

## ファイルのサイズを使ってソートする機能
#
#  ファイルのサイズを使ってアイテムをソートするための機能です。\n\n
#
#  CraftMailerでは、ソータと呼ばれるオブジェクトを使って、ファイルリストのアイテムを並べ替えて表示することが出来ます。\n
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
        return cmp( left.size(), right.size() ) * self.order

## ファイルのタイムスタンプを使ってソートする機能
#
#  ファイルのタイムスタンプを使ってアイテムをソートするための機能です。\n\n
#
#  CraftMailerでは、ソータと呼ばれるオブジェクトを使って、ファイルリストのアイテムを並べ替えて表示することが出来ます。\n
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
                        item.select(True)
                except KeyError:
                    continue

        self.delayedUpdateInfo()

    def _callFilterAndSorter(self):

        if self.item_filter:
            self.back_items = filter( self.item_filter, self.original_items )
        else:
            self.back_items = self.original_items[:]

        if self.sorter:
            self.back_items.sort( self.sorter )

    def delayedUpdateInfo(self):

        def jobUpdateInfo(job_item):
            self.disk_size_info = ckit.getDiskSize( os.path.splitdrive(self.getLocation())[0] )

        def jobUpdateInfoFinished(job_item):
            if job_item.isCanceled() : return
            self.main_window.paint(cmailer_mainwindow.PAINT_LEFT_FOOTER)

        self.disk_size_info = None
        if self.job_item:
            self.job_item.cancel()
            self.job_item = None
        self.job_item = ckit.JobItem( jobUpdateInfo, jobUpdateInfoFinished )
        self.job_queue.enqueue(self.job_item)

    def _updateInfo(self):

        self.num_file = 0
        self.num_dir = 0
        self.num_file_selected = 0
        self.num_dir_selected = 0
        self.selected_size = 0

        for item in self.items:
            self.num_file += 1
            if item.selected():
                self.num_file_selected += 1
                self.selected_size += item.size()

    def selectItem( self, i, sel=None ):

        item = self.items[i]
        sel_prev = self.items[i].selected()
        item.select(sel)

        if item.selected() != sel_prev:
            if item.selected():
                self.num_file_selected += 1
                self.selected_size += item.size()
            else:
                self.num_file_selected -= 1
                self.selected_size -= item.size()

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

