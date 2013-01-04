import os
import sys
import gc
import re
import math
import time
import cProfile
import fnmatch
import threading
import zipfile
import tarfile
import ConfigParser
import traceback
import msvcrt
import locale
import StringIO

import pyauto

import ckit
from ckit.ckit_const import *

#import cmailer_grepwindow
#import cmailer_textviewer
#import cmailer_configmenu
#import cmailer_wallpaper
#import cmailer_misc
#import cmailer_native

import cmailer_email
import cmailer_resource
import cmailer_listwindow
import cmailer_isearch
import cmailer_msgbox
import cmailer_statusbar
import cmailer_commandline
import cmailer_history
import cmailer_debug


MessageBox = cmailer_msgbox.MessageBox

os.stat_float_times(False)

## @addtogroup mainwindow メインウインドウ機能
## @{

#--------------------------------------------------------------------

class Log:

    def __init__(self):
        self.lock = threading.Lock()
        self.log = [u""]
        self.last_line_terminated = False

    def write(self,s):
        self.lock.acquire()
        try:
            if type(s)!=type(u''):
                s = unicode(s,'mbcs')
            while True:
                return_pos = s.find("\n")
                if return_pos < 0 : break
                if self.last_line_terminated:
                    self.log.append(u"")
                self.log[-1] += s[:return_pos]
                s = s[return_pos+1:]
                self.last_line_terminated = True
            if len(s)>0 :
                if self.last_line_terminated:
                    self.log.append(u"")
                self.log[-1] += s
                self.last_line_terminated = False
            if len(self.log)>1000:
                self.log = self.log[-1000:]
        finally:
            self.lock.release()

    def numLines(self):
        return len(self.log)

    def getLine(self,lineno):
        try:
            return self.log[lineno]
        except IndexError:
            return u""

#--------------------------------------------------------------------

class History:

    def __init__(self):
        self.items = []

    def append( self, path, cursor_filename, visible=True, mark=False ):
        for i in xrange(len(self.items)):
            if self.items[i][0]==path:
                if self.items[i][3] : mark=True
                del self.items[i]
                break
        self.items.insert( 0, ( path, cursor_filename, visible, mark ) )

        if len(self.items)>100:
            self.items = self.items[:100]

    def remove( self, path ):
        for i in xrange(len(self.items)):
            if self.items[i][0]==path:
                del self.items[i]
                return
        raise KeyError        

    def find( self, path ):
        for item in self.items:
            if item[0]==path:
                return item
        return None

    def findStartWith( self, path ):
        for item in self.items:
            if item[0][:len(path)].upper()==path.upper():
                return item
        return None

    def findLastVisible(self):
        for item in self.items:
            if item[2]:
                return item
        return None

    def save( self, ini, section ):
        i=0
        for item in self.items:
            if item[2]:
                ini.set( section, "history_%d"%(i,), item[0].encode("utf8") )
                i+=1

        while True:
            if not ini.remove_option( section, "history_%d"%(i,) ) : break
            i+=1

    def load( self, ini, section ):
        for i in xrange(100):
            try:
                item = ( ckit.normPath(unicode( ini.get( section, "history_%d"%(i,) ), "utf8" )), "", True, False )
                self.items.append(item)
            except:
                break

#--------------------------------------------------------------------

class MouseInfo:
    def __init__( self, mode, **args ):
        self.mode = mode
        self.__dict__.update(args)

#--------------------------------------------------------------------

PAINT_LEFT_LOCATION      = 1<<0
PAINT_LEFT_HEADER        = 1<<1
PAINT_LEFT_ITEMS         = 1<<2
PAINT_LEFT_FOOTER        = 1<<3

PAINT_FOCUSED_LOCATION   = 1<<8
PAINT_FOCUSED_HEADER     = 1<<9
PAINT_FOCUSED_ITEMS      = 1<<10
PAINT_FOCUSED_FOOTER     = 1<<11

PAINT_LOG                = 1<<13
PAINT_STATUS_BAR         = 1<<14

PAINT_LEFT               = PAINT_LEFT_LOCATION | PAINT_LEFT_HEADER | PAINT_LEFT_ITEMS | PAINT_LEFT_FOOTER
PAINT_FOCUSED            = PAINT_FOCUSED_LOCATION | PAINT_FOCUSED_HEADER | PAINT_FOCUSED_ITEMS | PAINT_FOCUSED_FOOTER
PAINT_UPPER              = PAINT_LEFT
PAINT_ALL                = 0xffffffff

## メーラのメインウインドウ
#
#  メーラの主な機能を実現しているクラスです。\n\n
#  設定ファイル config.py の configure に渡される window 引数は、MainWindow クラスのオブジェクトです。
#
class MainWindow( ckit.Window ):

    FOCUS_LEFT  = 0

    def __init__( self, config_filename, ini_filename, mbox_dirname, debug=False, profile=False ):
    
        self.initialized = False
        self.quit_required = True
        self.top_level_quitting = False
        
        self.config_filename = config_filename

        self.debug = debug
        self.profile = profile
        
        self.ini = ConfigParser.RawConfigParser()
        self.ini_filename = ini_filename
        
        self.mbox_dirname = mbox_dirname

        self.loadState()

        self.loadTheme()

        ckit.Window.__init__(
            self,
            x=self.ini.getint( "GEOMETRY", "x" ),
            y=self.ini.getint( "GEOMETRY", "y" ),
            width=self.ini.getint( "GEOMETRY", "width" ),
            height=self.ini.getint( "GEOMETRY", "height" ),
            font_name = unicode( self.ini.get( "FONT", "name" ), "utf8" ),
            font_size = self.ini.getint( "FONT", "size" ),
            bg_color = ckit.getColor("bg"),
            cursor0_color = ckit.getColor("cursor0"),
            cursor1_color = ckit.getColor("cursor1"),
            border_size = 2,
            title_bar = True,
            title = cmailer_resource.cmailer_appname,
            cursor = True,
            sysmenu=True,
            activate_handler = self._onActivate,
            close_handler = self._onClose,
            move_handler = self._onMove,
            size_handler = self._onSize,
            keydown_handler = self._onKeyDown,
            keyup_handler = self._onKeyUp,
            char_handler = self._onChar,
            lbuttondown_handler = self._onLeftButtonDownOutside,
            lbuttonup_handler = self._onLeftButtonUpOutside,
            mbuttondown_handler = self._onMiddleButtonDownOutside,
            mbuttonup_handler = self._onMiddleButtonUpOutside,
            rbuttondown_handler = self._onRightButtonDownOutside,
            rbuttonup_handler = self._onRightButtonUpOutside,
            lbuttondoubleclick_handler = self._onLeftButtonDoubleClickOutside,
            mousemove_handler = self._onMouseMoveOutside,
            mousewheel_handler= self._onMouseWheelOutside,
            )

        self.updateColor()

        if self.ini.getint( "DEBUG", "detect_block" ):
            cmailer_debug.enableBlockDetector()

        if self.ini.getint( "DEBUG", "print_errorinfo" ):
            cmailer_debug.enablePrintErrorInfo()

        self.setCursorPos( -1, -1 )

        self.updateHotKey()

        self.focus = MainWindow.FOCUS_LEFT
        self.log_window_height = self.ini.getint( "GEOMETRY", "log_window_height" )

        self.command = ckit.CommandMap(self)

        self.status_bar = cmailer_statusbar.StatusBar()
        self.status_bar_layer = cmailer_statusbar.SimpleStatusBarLayer()
        self.status_bar_resistered = False
        self.status_bar_paint_hook = None
        self.commandline_edit = None
        self.progress_bar = None

        #self.bookmark = cmailer_bookmark.Bookmark()
        #self.bookmark.load( self.ini, "BOOKMARK" )

        self.inbox_folder = cmailer_email.Folder( os.path.join( self.mbox_dirname, "inbox.mbox" ) )

        self.account = cmailer_email.Account(
            self.ini,
            cmailer_email.Pop3Receiver(
                self.ini.get( "ACCOUNT", "server" ),
                self.ini.getint( "ACCOUNT", "port" ),
                self.ini.get( "ACCOUNT", "username" ),
                self.ini.get( "ACCOUNT", "password" )
            ),
            None
        )

        class Pane:
            pass

        self.upper_pane = Pane()
        #self.upper_pane.history = History()
        #self.upper_pane.history.load( self.ini, "LEFTPANE" )
        #self.upper_pane.found_prefix = u""
        #self.upper_pane.found_location = u""
        #self.upper_pane.found_items = []
        self.upper_pane.file_list = cmailer_email.FileList( self, cmailer_email.lister_Empty() )
        self.upper_pane.scroll_info = ckit.ScrollInfo()
        self.upper_pane.cursor = 0
        self.upper_pane.footer_paint_hook = None

        self.upper_pane.edit = ckit.TextWidget( self, 0, 0, 0, 0, message_handler=self.setStatusMessage )
        doc = ckit.Document( filename=None, mode=ckit.TextMode() )
        doc.setReadOnly(True)
        doc.setBGColor(None)
        self.upper_pane.edit.setDocument(doc)
        self.upper_pane.edit.scroll_margin_v = 0
        self.upper_pane.edit.scroll_bottom_adjust = True
        self.upper_pane.edit.show_lineno = False
        self.upper_pane.edit.doc.mode.show_tab = False
        self.upper_pane.edit.doc.mode.show_space = False
        self.upper_pane.edit.doc.mode.show_wspace = False
        self.upper_pane.edit.doc.mode.show_lineend = False
        self.upper_pane.edit.doc.mode.show_fileend = False
        self.upper_pane.edit.show(False)

        self.log_pane = Pane()
        self.log_pane.log = Log()
        self.log_pane.scroll_info = ckit.ScrollInfo()
        self.log_pane.selection = [ [ 0, 0 ], [ 0, 0 ] ]

        self.keymap = ckit.Keymap()
        #self.jump_list = []
        #self.filter_list = []
        #self.select_filter_list = []
        self.sorter_list = []
        #self.association_list = []
        self.itemformat_list = []
        self.itemformat = cmailer_email.itemformat_Name_Ext_Size_YYMMDD_HHMMSS
        #self.editor = u"notepad.exe"
        #self.diff_editor = None
        #self.commandline_list = []

        self.commandline_history = cmailer_history.History(1000)
        self.commandline_history.load( self.ini, "COMMANDLINE" )
        """
        self.pattern_history = cmailer_history.History()
        self.pattern_history.load( self.ini, "PATTERN" )
        self.search_history = cmailer_history.History()
        self.search_history.load( self.ini, "SEARCH" )
        """
        
        self.launcher = cmailer_commandline.commandline_Launcher(self)

        self.keydown_hook = None
        self.char_hook = None
        self.enter_hook = None
        self.mouse_event_mask = False
        
        self.mouse_click_info = None

        self.migemo = None

        self.task_queue_stack = []
        self.synccall = ckit.SyncCall()

        self.user_input_ownership = threading.Lock()
        
        self.setTimer( self.onTimerJob, 10 )
        self.setTimer( self.onTimerSyncCall, 10 )

        try:
            self.createThemePlane()
        except:
            cmailer_debug.printErrorInfo()

        try:
            self.wallpaper = None
            self.updateWallpaper()
        except:
            self.wallpaper = None

        self.initialized = True
        self.quit_required = False

        self.paint()

    def destroy(self):
        #self.upper_pane.file_list.destroy()
        cmailer_debug.disableBlockDetector()
        ckit.Window.destroy(self)

    def messageLoop( self, continue_cond_func=None ):
        if not continue_cond_func:
            def defaultLoopCond():
                if self.quit_required:
                    self.quit_required = False
                    return False
                return True
            continue_cond_func = defaultLoopCond
        ckit.Window.messageLoop( self, continue_cond_func )

    def topLevelMessageLoop(self):
        def isLoopContinue():
            if self.quit_required:
                self.top_level_quitting = True
                self.enable(False)
                if self.task_queue_stack:
                    for task_queue in self.task_queue_stack:
                        task_queue.cancel()
                    return True
                return False
            return True
        self.messageLoop(isLoopContinue)

    def quit(self):
        self.quit_required = True
    
    def isQuitting(self):
        return self.top_level_quitting
    

    ## ユーザ入力権を獲得する
    #
    #  @param self      -
    #  @param blocking  ユーザ入力権を獲得するまでブロックするか
    #
    #  CraftMailerをマウスやキーボードで操作させる権利を獲得するための関数です。\n\n
    #
    #  バックグラウンド処理の途中や最後でユーザの操作を受け付ける場合には、
    #  releaseUserInputOwnership と releaseUserInputOwnership を使って、
    #  入力権を所有する必要があります。
    #  さもないと、フォアグラウンドのユーザ操作と衝突してしまい、ユーザが混乱したり、
    #  CraftMailerが正しく動作しなくなります。\n\n
    #
    #  @sa releaseUserInputOwnership
    #
    def acquireUserInputOwnership( self, blocking=1 ):
        return self.user_input_ownership.acquire(blocking)
    
    ## ユーザ入力権を解放する
    #
    #  @sa acquireUserInputOwnership
    #
    def releaseUserInputOwnership(self):
        self.user_input_ownership.release()

    def onTimerJob(self):
        
        # タスクキューが空っぽだったら破棄する
        if len(self.task_queue_stack)>0:
            if self.task_queue_stack[-1].numItems()==0:
                self.task_queue_stack[-1].cancel()
                self.task_queue_stack[-1].join()
                self.task_queue_stack[-1].destroy()
                del self.task_queue_stack[-1]

                # 新しくアクティブになったタスクキューを再開する
                if len(self.task_queue_stack)>0:
                    self.task_queue_stack[-1].restart()
        
        if not self.acquireUserInputOwnership(False) : return
        try:
            ckit.JobQueue.checkAll()
        finally:
            self.releaseUserInputOwnership()

    def onTimerSyncCall(self):
        self.synccall.check()


    ## サブスレッドで処理を実行する
    #
    #  @param self              -
    #  @param func              サブスレッドで実行する呼び出し可能オブジェクト
    #  @param arg               引数 func に渡す引数
    #  @param cancel_func       ESCキーが押されたときのキャンセル処理
    #  @param cancel_func_arg   引数 cancel_func に渡す引数
    #  @param raise_error       引数 func のなかで例外が発生したときに、それを raise するか
    #
    #  メインスレッドのユーザインタフェイスの更新を止めずに、サブスレッドの中で任意の処理を行うための関数です。\n\n
    #
    #  この関数のなかでは、引数 func をサブスレッドで呼び出しながら、メインスレッドでメッセージループを回します。
    #  返値には、引数 func の返値がそのまま返ります。\n\n
    #
    #  ファイルのコピーや画像のデコードなどの、比較的時間のかかる処理は、メインスレッドではなくサブスレッドの中で処理するように心がけるべきです。
    #  さもないと、メインスレッドがブロックし、ウインドウの再描画などが長時間されないままになるといった弊害が発生します。
    #
    def subThreadCall( self, func, arg, cancel_func=None, cancel_func_arg=(), raise_error=False ):

        class SubThread( threading.Thread ):

            def __init__( self, main_window ):
                threading.Thread.__init__(self)
                self.main_window = main_window
                self.result = None
                self.error = None

            def run(self):
                ckit.setBlockDetector()
                try:
                    self.result = func(*arg)
                except Exception, e:
                    cmailer_debug.printErrorInfo()
                    self.error = e

        def onKeyDown( vk, mod ):
            if vk==VK_ESCAPE:
                if cancel_func:
                    cancel_func(*cancel_func_arg)
            return True

        def onChar( ch, mod ):
            return True

        keydown_hook_old = self.keydown_hook
        char_hook_old = self.char_hook
        mouse_event_mask_old = self.mouse_event_mask

        sub_thread = SubThread(self)
        sub_thread.start()

        self.keydown_hook = onKeyDown
        self.char_hook = onChar
        self.mouse_event_mask = True

        self.removeKeyMessage()
        self.messageLoop( sub_thread.isAlive )

        sub_thread.join()
        result = sub_thread.result
        error = sub_thread.error
        del sub_thread

        self.keydown_hook = keydown_hook_old
        self.char_hook = char_hook_old
        self.mouse_event_mask = mouse_event_mask_old

        if error:
            if raise_error:
                raise error
            else:
                print error
        
        return result

    ## コンソールプログラムをサブプロセスとして実行する
    #
    #  @param self              -
    #  @param cmd               コマンドと引数のシーケンス
    #  @param cwd               サブプロセスのカレントディレクトリ
    #  @param env               サブプロセスの環境変数
    #  @param enable_cancel     True:ESCキーでキャンセルする  False:ESCキーでキャンセルしない
    #
    #  任意のコンソールプログラムを、メーラのサブプロセスとして実行し、そのプログラムの出力を、ログペインにリダイレクトします。\n\n
    #
    #  引数 cmd には、サブプロセスとして実行するプログラムと引数をリスト形式で渡します。\n
    #  例:  [ "subst", "R:", "//remote-machine/public/" ]
    #
    def subProcessCall( self, cmd, cwd=None, env=None, enable_cancel=False ):

        p = ckit.SubProcess(cmd,cwd,env)
        
        if enable_cancel:
            cancel_handler = p.cancel
        else:
            cancel_handler = None

        return self.subThreadCall( p, (), cancel_handler )

    ## バックグラウンドタスクのキューに、タスクを投入する
    #
    #  @param self              -
    #  @param job_item          バックグラウンドタスクとして実行する JobItem オブジェクト
    #  @param comment           ユーザに説明する際のタスクの名前
    #  @param create_new_queue  新しいタスクキューを作成し、優先的に処理するか。( True:作成する  False:作成しない  None:問い合わせる )
    #
    #  CraftMailerはバックグランド処理をサポートしており、ファイルのコピーや検索などの時間のかかる処理をバックグラウンドで実行しながら、
    #  ほかのディレクトリを閲覧したり、次に実行するバックグランド処理を予約したりすることが出来ます。\n\n
    #
    #  バックグランド処理は、複数予約することが出来ますが、同時に実行することが出来るのは１つだけで、キュー(待ち行列)に投入されて、
    #  順番に処理されます。
    #
    def taskEnqueue( self, job_item, comment=u"", create_new_queue=None ):
    
        if len(self.task_queue_stack)>0:
            if create_new_queue==None:
                result = cmailer_msgbox.popMessageBox( self, MessageBox.TYPE_YESNO, u"タスクの処理順序の確認", u"優先的に処理を行いますか？" )
                if result==MessageBox.RESULT_YES:
                    create_new_queue = True
                elif result==MessageBox.RESULT_NO:
                    create_new_queue = False
                else:
                    return
        else:
            create_new_queue = True

        # メッセージダイアログ中にキューが空っぽになった場合は、キューを作成する
        if len(self.task_queue_stack)==0:
            create_new_queue = True

        if create_new_queue:

            new_task_queue = ckit.JobQueue()
        
            # まず前のタスクキューをポーズする処理を投入する
            if len(self.task_queue_stack)>0:

                prev_task_queue = self.task_queue_stack[-1]
                def jobPause( job_item ):
                    prev_task_queue.pause()
                pause_job_item = ckit.JobItem( jobPause, None )
                new_task_queue.enqueue(pause_job_item)

            self.task_queue_stack.append(new_task_queue)
        
        else:    
            if comment and self.task_queue_stack[-1].numItems()>0:
                self.setStatusMessage( u"タスクを予約しました : %s" % comment, 3000 )

        self.task_queue_stack[-1].enqueue(job_item)

    ## コマンドラインで文字列を入力する
    #
    #  @param self                      -
    #  @param title                     コマンド入力欄の左側に表示されるタイトル文字列
    #  @param text                      コマンド入力欄の初期文字列
    #  @param selection                 コマンド入力欄の初期選択範囲
    #  @param auto_complete             自動補完を有効にするか
    #  @param autofix_list              入力確定をする文字のリスト
    #  @param return_modkey             入力欄が閉じたときに押されていたモディファイアキーを取得するか
    #  @param update_handler            コマンド入力欄の変更があったときに通知を受けるためのハンドラ
    #  @param candidate_handler         補完候補を列挙するためのハンドラ
    #  @param candidate_remove_handler  補完候補を削除するためのハンドラ
    #  @param status_handler            コマンド入力欄の右側に表示されるステータス文字列を返すためのハンドラ
    #  @param enter_handler             コマンド入力欄でEnterキーが押されたときのハンドラ
    #  @return                          入力された文字列
    #
    #  CraftMailerのメインウインドウの下端のステータスバーの領域をつかって、任意の文字列の入力を受け付けるための関数です。\n\n
    #
    def commandLine( self, title, text=u"", selection=None, auto_complete=False, autofix_list=None, return_modkey=False, update_handler=None, candidate_handler=None, candidate_remove_handler=None, status_handler=None, enter_handler=None ):

        title = u" " + title + u" "
        title_width = self.getStringWidth(title)
        status_string = [ u"" ]
        result = [ None ]
        result_mod = [ 0 ]

        class CommandLine:

            def __init__( self, main_window ):
                self.main_window = main_window

            def _onKeyDown( self, vk, mod ):
                
                result_mod[0] = mod

                if self.main_window.commandline_edit.onKeyDown( vk, mod ):
                    return True

                if vk==VK_RETURN:
                    result[0] = self.main_window.commandline_edit.getText()
                    if enter_handler:
                        self.closeList()
                        if enter_handler( self, result[0], mod ):
                            return True
                    self.quit()
                elif vk==VK_ESCAPE:
                    if self.main_window.commandline_edit.getText():
                        self.main_window.commandline_edit.clear()
                    else:
                        self.quit()
                return True

            def _onChar( self, ch, mod ):
                result_mod[0] = mod
                self.main_window.commandline_edit.onChar( ch, mod )
                return True

            def _onUpdate( self, update_info ):
                if update_handler:
                    if not update_handler(update_info):
                        return False
                if status_handler:
                    status_string[0] = status_handler(update_info)
                    self.main_window.paint(PAINT_STATUS_BAR)

            def _onPaint( self, x, y, width, height ):

                status_string_for_paint = u" " + status_string[0] + u" "
                status_width = self.main_window.getStringWidth(status_string_for_paint)

                attr = ckit.Attribute( fg=ckit.getColor("bar_fg"))

                self.main_window.putString( x, y, title_width, height, attr, title )
                self.main_window.putString( x+width-status_width, y, status_width, height, attr, status_string_for_paint )

                if self.main_window.theme_enabled:

                    client_rect = self.main_window.getClientRect()
                    offset_x, offset_y = self.main_window.charToClient( 0, 0 )
                    char_w, char_h = self.main_window.getCharSize()
                    frame_width = 2

                    self.main_window.plane_statusbar.setPosSize( 0, (self.main_window.height()-1)*char_h+offset_y-frame_width, client_rect[2], client_rect[3]-((self.main_window.height()-1)*char_h+offset_y-frame_width) )
                    self.main_window.plane_commandline.setPosSize( title_width*char_w+offset_x, (self.main_window.height()-1)*char_h+offset_y-frame_width, client_rect[2]-((title_width+status_width)*char_w+offset_x), char_h+frame_width*2 )

                self.main_window.commandline_edit.setPosSize( x+title_width, y, width-title_width-status_width, height )
                self.main_window.commandline_edit.enableCursor(True)
                self.main_window.commandline_edit.paint()

            def getText(self):
                return self.main_window.commandline_edit.getText()
            
            def setText( self, text ):
                self.main_window.commandline_edit.setText(text)

            def getSelection(self):
                return self.main_window.commandline_edit.getSelection()

            def setSelection(self,selection):
                self.main_window.commandline_edit.setSelection(selection)

            def selectAll(self):
                self.main_window.commandline_edit.selectAll()

            def closeList(self):
                self.main_window.commandline_edit.closeList()

            def appendHistory(self,newentry):
                self.main_window.commandline_history.append(newentry)

            def quit(self):
                self.main_window.quit()

        commandline_edit_old = self.commandline_edit
        keydown_hook_old = self.keydown_hook
        char_hook_old = self.char_hook
        mouse_event_mask_old = self.mouse_event_mask
        status_bar_paint_hook_old = self.status_bar_paint_hook

        commandline = CommandLine(self)

        self.commandline_edit = ckit.EditWidget( self, title_width, self.height()-1, self.width()-title_width, 1, text, selection, auto_complete=auto_complete, no_bg=True, autofix_list=autofix_list, update_handler=commandline._onUpdate, candidate_handler=candidate_handler, candidate_remove_handler=candidate_remove_handler )
        self.keydown_hook = commandline._onKeyDown
        self.char_hook = commandline._onChar
        self.mouse_event_mask = True
        self.status_bar_paint_hook = commandline._onPaint

        if status_handler:
            status_string[0] = status_handler(ckit.EditWidget.UpdateInfo(text,selection))

        if self.theme_enabled:
            self.plane_commandline.show(True)

        self.paint(PAINT_STATUS_BAR)

        self.removeKeyMessage()
        self.messageLoop()

        self.commandline_edit.destroy()

        self.enableIme(False)

        self.commandline_edit = commandline_edit_old
        self.keydown_hook = keydown_hook_old
        self.char_hook = char_hook_old
        self.mouse_event_mask = mouse_event_mask_old
        self.status_bar_paint_hook = status_bar_paint_hook_old

        if self.theme_enabled:
            self.plane_commandline.show(False)

        self.setCursorPos( -1, -1 )
        self.updatePaneRect()

        self.paint(PAINT_STATUS_BAR)
        
        if return_modkey:
            return result[0], result_mod[0]
        else:    
            return result[0]

    def _onActivate( self, active ):
        self.active = active

    def _onClose( self ):
        self.quit()

    def _onMove( self, x, y ):

        if not self.initialized : return

        if self.commandline_edit:
            self.commandline_edit.onWindowMove()

    def _onSize( self, width, height ):

        if not self.initialized : return
        
        if self.log_window_height>height-4 : self.log_window_height=height-4
        if self.log_window_height<0 : self.log_window_height=0
        self.upper_pane.scroll_info.makeVisible( self.upper_pane.cursor, self.fileListItemPaneHeight(), 1 )

        self.updatePaneRect()
        
        if self.wallpaper:
            self.wallpaper.adjust()

        self.paint()

    def _onKeyDown( self, vk, mod ):

        pane = self.activePane()
        #print "_onKeyDown", vk, mod

        if self.keydown_hook:
            if self.keydown_hook( vk, mod ):
                return True

        selected = 0
        if pane.file_list.selected():
            selected = 1

        if not self.acquireUserInputOwnership(False) : return
        try:
            # アクティブなTextWidgetのキー処理
            if pane.edit.visible:
                result = [None]
                if self.profile:
                    cProfile.runctx( "result[0] = pane.edit.onKeyDown( vk, mod )", globals(), locals() )
                else:
                    result[0] = pane.edit.onKeyDown( vk, mod )
                if result[0]:
                    return result[0]

            # メインウインドウのキー処理
            try:
                func = self.keymap.table[ ckit.KeyEvent(vk,mod,extra=selected) ]
                if self.profile:
                    cProfile.runctx( "func()", globals(), locals() )
                else:
                    func()
            except KeyError:
                pass
        finally:
            self.releaseUserInputOwnership()

        return True

    def _onKeyUp( self, vk, mod ):

        #print "_onKeyUp", vk, mod
        pass

    def _onChar( self, ch, mod ):

        pane = self.activePane()
        #print "_onChar", ch, mod

        if self.char_hook:
            if self.char_hook( ch, mod ):
                return

        if not self.acquireUserInputOwnership(False) : return
        try:

            # アクティブなTextEditWidgetの文字入力処理
            if pane.edit.visible:
                result = [None]
                if self.profile:
                    cProfile.runctx( "result[0] = pane.edit.onChar( ch, mod )", globals(), locals() )
                else:
                    result[0] = pane.edit.onChar( ch, mod )
                if result[0]:
                    return result[0]

        finally:
            self.releaseUserInputOwnership()


    def _onLeftButtonDownOutside( self, x, y, mod ):
        if not self.acquireUserInputOwnership(False) : return
        try:
            self._onLeftButtonDown(x, y, mod)
        finally:
            self.releaseUserInputOwnership()

    def _onLeftButtonUpOutside( self, x, y, mod ):
        if not self.acquireUserInputOwnership(False) : return
        try:
            self._onLeftButtonUp(x, y, mod)
        finally:
            self.releaseUserInputOwnership()

    def _onMiddleButtonDownOutside( self, x, y, mod ):
        if not self.acquireUserInputOwnership(False) : return
        try:
            self._onMiddleButtonDown(x, y, mod)
        finally:
            self.releaseUserInputOwnership()

    def _onMiddleButtonUpOutside( self, x, y, mod ):
        if not self.acquireUserInputOwnership(False) : return
        try:
            self._onMiddleButtonUp(x, y, mod)
        finally:
            self.releaseUserInputOwnership()

    def _onRightButtonDownOutside( self, x, y, mod ):
        if not self.acquireUserInputOwnership(False) : return
        try:
            self._onRightButtonDown(x, y, mod)
        finally:
            self.releaseUserInputOwnership()

    def _onRightButtonUpOutside( self, x, y, mod ):
        if not self.acquireUserInputOwnership(False) : return
        try:
            self._onRightButtonUp(x, y, mod)
        finally:
            self.releaseUserInputOwnership()

    def _onLeftButtonDoubleClickOutside( self, x, y, mod ):
        if not self.acquireUserInputOwnership(False) : return
        try:
            self._onLeftButtonDoubleClick(x, y, mod)
        finally:
            self.releaseUserInputOwnership()

    def _onMouseMoveOutside( self, x, y, mod ):
        if not self.acquireUserInputOwnership(False) : return
        try:
            self._onMouseMove(x, y, mod)
        finally:
            self.releaseUserInputOwnership()

    def _onMouseWheelOutside( self, x, y, wheel, mod ):
        if not self.acquireUserInputOwnership(False) : return
        try:
            self._onMouseWheel(x, y, wheel, mod)
        finally:
            self.releaseUserInputOwnership()

    def _mouseCommon( self, x, y, focus=True ):

        client_rect = self.getClientRect()
        offset_x, offset_y = self.charToClient( 0, 0 )
        char_w, char_h = self.getCharSize()

        char_x = (x-offset_x) / char_w
        char_y = (y-offset_y) / char_h
        sub_x = float( (x-offset_x) - char_x * char_w ) / char_w
        sub_y = float( (y-offset_y) - char_y * char_h ) / char_h
        
        upper_pane_rect = list( self.leftPaneRect() )
        log_pane_rect = list( self.logPaneRect() )

        region = None
        pane = None
        pane_rect = None

        if upper_pane_rect[0]<=char_x<upper_pane_rect[2] and upper_pane_rect[1]<=char_y<upper_pane_rect[3]:

            if upper_pane_rect[1]==char_y:
                region = PAINT_LEFT_LOCATION
                pane = self.upper_pane
                pane_rect = [ upper_pane_rect[0], upper_pane_rect[1], upper_pane_rect[2], upper_pane_rect[1]+1 ]
            elif upper_pane_rect[1]+2<=char_y<upper_pane_rect[3]-1:
                region = PAINT_LEFT_ITEMS
                pane = self.upper_pane
                pane_rect = [ upper_pane_rect[0], upper_pane_rect[1]+2, upper_pane_rect[2], upper_pane_rect[3]-1 ]

        elif log_pane_rect[0]<=char_x<log_pane_rect[2] and log_pane_rect[1]<=char_y<log_pane_rect[3]:
            region = PAINT_LOG
            pane = self.log_pane
            pane_rect = log_pane_rect

        return [ char_x, char_y, sub_x, sub_y, region, pane, pane_rect ]

    def _charPosToLogPos( self, char_x, char_y ):
        
        log_pane_rect = list( self.logPaneRect() )
        
        char_x = max(char_x,log_pane_rect[0])
        char_x = min(char_x,log_pane_rect[2])
        
        if char_y < log_pane_rect[1]:
            char_x = 0
            char_y = log_pane_rect[1]

        if char_y > log_pane_rect[3]:
            char_x = log_pane_rect[2]
            char_y = log_pane_rect[3]

        lineno = self.log_pane.scroll_info.pos + char_y - log_pane_rect[1]

        s = self.log_pane.log.getLine(lineno)
        
        w = 0
        char_index = 0
        for char_index in xrange(len(s)):
            w += self.getStringWidth(s[char_index])
            if w > char_x : break
        else:
            char_index = len(s)
        
        return lineno, char_index

    def _onLeftButtonDown( self, x, y, mod ):
        #print "_onLeftButtonDown", x, y

        if self.mouse_event_mask : return

        self.mouse_click_info=None

        active_pane_prev = self.activePane()

        char_x, char_y, sub_x, sub_y, region, pane, pane_rect = self._mouseCommon( x, y, True )

        if region==PAINT_LEFT_ITEMS:
        
            if pane.edit.visible:
                pane.edit.onLeftButtonDown( char_x, char_y, sub_x, sub_y, mod )
                self.setCapture()
                self.mouse_click_info = MouseInfo( "edit", x=x, y=y, mod=mod, pane=pane )
            else:
                item_index = char_y-pane_rect[1]+pane.scroll_info.pos
                if item_index<pane.file_list.numItems():
            
                    item = pane.file_list.getItem(item_index)
            
                    if mod & MODKEY_SHIFT and active_pane_prev==self.activePane():
                        while 1:
                            pane.file_list.selectItem( pane.cursor, True )
                            if item_index>pane.cursor : pane.cursor+=1
                            elif item_index<pane.cursor : pane.cursor-=1
                            else : break
            
                    elif not (mod & MODKEY_CTRL):
                        if not item.selected():
                            for i in xrange(pane.file_list.numItems()):
                                pane.file_list.selectItem( i, False )
                        pane.cursor = item_index
                        pane.file_list.selectItem(pane.cursor,True)

                    self.paint( PAINT_FOCUSED_ITEMS | PAINT_FOCUSED_HEADER )

                # ドラッグ＆ドロップの準備
                dnd_items = []

                self.mouse_click_info = MouseInfo( "item", x=x, y=y, mod=mod, dnd_items=dnd_items )

        elif region==PAINT_LOG:
            
            lineno, char_index = self._charPosToLogPos( char_x, char_y )
            
            self.mouse_click_info = MouseInfo( "log", x=x, y=y, lineno=lineno, char_index=char_index )
            self.setCapture()
            
            self.log_pane.selection = [
                [ lineno, char_index ],
                [ lineno, char_index ]
                ]

            self.paint(PAINT_LOG)    


    def _onLeftButtonUp( self, x, y, mod ):
        #print "_onLeftButtonUp", x, y

        if self.mouse_event_mask : return

        if self.mouse_click_info==None : return
        
        if self.mouse_click_info.mode=="edit":
            char_x, char_y, sub_x, sub_y, region, pane, pane_rect = self._mouseCommon( x, y, False )
            self.mouse_click_info.pane.edit.onLeftButtonUp( char_x, char_y, sub_x, sub_y, mod )
            self.releaseCapture()
            self.mouse_click_info = None

        elif self.mouse_click_info.mode=="item":

            x, y, mod = self.mouse_click_info.x, self.mouse_click_info.y, self.mouse_click_info.mod
            self.mouse_click_info = None

            char_x, char_y, sub_x, sub_y, region, pane, pane_rect = self._mouseCommon( x, y, True )

            if region==PAINT_LEFT_ITEMS:

                # 選択を解除
                if not (mod & (MODKEY_CTRL|MODKEY_SHIFT)):
                    for i in xrange(pane.file_list.numItems()):
                        pane.file_list.selectItem( i, False )

                # カーソル移動とアイテム選択
                item_index = char_y-pane_rect[1]+pane.scroll_info.pos
                if item_index<pane.file_list.numItems():
                    pane.cursor = item_index
                    if mod & MODKEY_CTRL:
                        pane.file_list.selectItem(pane.cursor)
                    else:
                        pane.file_list.selectItem(pane.cursor,True)

                self.paint( PAINT_FOCUSED_ITEMS | PAINT_FOCUSED_HEADER )

        elif self.mouse_click_info.mode in ( "log", "log_double_click" ):
            self.mouse_click_info=None
            self.releaseCapture()
            return

    def _onLeftButtonDoubleClick( self, x, y, mod ):
        #print "_onLeftButtonDoubleClick", x, y

        if self.mouse_event_mask : return

        self.mouse_click_info=None

        char_x, char_y, sub_x, sub_y, region, pane, pane_rect = self._mouseCommon( x, y, True )

        if region==PAINT_LEFT_ITEMS:
        
            if pane.edit.visible:
                pane.edit.onLeftButtonDoubleClick( char_x, char_y, sub_x, sub_y, mod )
                self.setCapture()
                self.mouse_click_info = MouseInfo( "edit", x=x, y=y, mod=mod, pane=pane )
            else:
                item_index = char_y-pane_rect[1]+pane.scroll_info.pos
                if item_index<pane.file_list.numItems():
                    pane.cursor = item_index
                    self.command.Enter()

        elif region==PAINT_LEFT_LOCATION:
            pass
        
        elif region==PAINT_LOG:
            
            lineno, char_index = self._charPosToLogPos( char_x, char_y )

            s = self.log_pane.log.getLine(lineno)
            left = max( ckit.wordbreak_TextFile( s, char_index, -1 ), 0 )
            right = min( ckit.wordbreak_TextFile( s, char_index+1, +1 ), len(s) )
            
            self.mouse_click_info = MouseInfo( "log_double_click", x=x, y=y, lineno=lineno, left=left, right=right )
            self.setCapture()
            
            self.log_pane.selection = [
                [ lineno, left ],
                [ lineno, right ]
                ]

            self.paint(PAINT_LOG)    


    def _onMiddleButtonDown( self, x, y, mod ):
        #print "_onMiddleButtonDown", x, y

        if self.mouse_event_mask : return

        self.mouse_click_info=None

        char_x, char_y, sub_x, sub_y, region, pane, pane_rect = self._mouseCommon( x, y, True )

    def _onMiddleButtonUp( self, x, y, mod ):
        #print "_onMiddleButtonUp", x, y

        if self.mouse_event_mask : return

        self.mouse_click_info = None

    def _onRightButtonDown( self, x, y, mod ):
        #print "_onRightButtonDown", x, y

        if self.mouse_event_mask : return

        self.mouse_click_info=None

        char_x, char_y, sub_x, sub_y, region, pane, pane_rect = self._mouseCommon( x, y, True )

        if region==PAINT_LEFT_ITEMS:

            if pane.edit.visible:
                pane.edit.onRightButtonDown( char_x, char_y, sub_x, sub_y, mod )
                self.mouse_click_info = MouseInfo( "edit", x=x, y=y, mod=mod, pane=pane )
            else:
                item_index = char_y-pane_rect[1]+pane.scroll_info.pos
                if item_index<pane.file_list.numItems():
                    pane.cursor = item_index
                    item = pane.file_list.getItem(pane.cursor)
                    if not item.selected():
                        for i in xrange(pane.file_list.numItems()):
                            pane.file_list.selectItem( i, False )
                        pane.file_list.selectItem(pane.cursor,True)
                    self.paint( PAINT_FOCUSED_ITEMS | PAINT_FOCUSED_HEADER )
                else:
                    for i in xrange(pane.file_list.numItems()):
                        pane.file_list.selectItem( i, False )
                    self.paint( PAINT_FOCUSED_ITEMS | PAINT_FOCUSED_HEADER )

                self.mouse_click_info = MouseInfo( "item", x=x, y=y, mod=mod, dnd_items=[] )

        elif region==PAINT_LEFT_LOCATION:
            self.mouse_click_info = MouseInfo( "item", x=x, y=y, mod=mod, dnd_items=[] )


    def _onRightButtonUp( self, x, y, mod ):
        #print "_onRightButtonUp", x, y

        if self.mouse_event_mask : return

        if self.mouse_click_info==None : return

        if self.mouse_click_info.mode=="edit":
            char_x, char_y, sub_x, sub_y, region, pane, pane_rect = self._mouseCommon( x, y, False )
            self.mouse_click_info.pane.edit.onRightButtonUp( char_x, char_y, sub_x, sub_y, mod )
            self.mouse_click_info=None

        elif self.mouse_click_info.mode=="item":
            x, y, mod = self.mouse_click_info.x, self.mouse_click_info.y, self.mouse_click_info.mod
            self.mouse_click_info = None

            char_x, char_y, sub_x, sub_y, region, pane, pane_rect = self._mouseCommon( x, y, True )

            if region==PAINT_LEFT_ITEMS:
                self.command.ContextMenu()
            elif region==PAINT_LEFT_LOCATION:
                self.command.ContextMenuDir()

    def _onMouseMove( self, x, y, mod ):
        #print "_onMouseMove", x, y
        
        if self.mouse_event_mask : return

        char_x, char_y, sub_x, sub_y, region, pane, pane_rect = self._mouseCommon( x, y, False )

        if self.mouse_click_info==None : return
        
        if self.mouse_click_info.mode=="edit":
            self.mouse_click_info.pane.edit.onMouseMove( char_x, char_y, sub_x, sub_y, mod )
        
        elif self.mouse_click_info.mode=="item":
        
            if abs(self.mouse_click_info.x-x)>8 or abs(self.mouse_click_info.y-y)>8:
                if len(self.mouse_click_info.dnd_items)>0:
                    cmailer_native.doDragAndDrop( self.mouse_click_info.dnd_items )
                self.mouse_click_info = None

        elif self.mouse_click_info.mode in ( "log", "log_double_click" ):
            char_x, char_y, sub_x, sub_y, region, pane, pane_rect = self._mouseCommon( x, y, False )
            
            log_pane_rect = list( self.logPaneRect() )
            if char_y < log_pane_rect[1]:
                self.command.LogUp()
            elif char_y >= log_pane_rect[3]:
                self.command.LogDown()

            lineno, char_index = self._charPosToLogPos( char_x, char_y )
                
            if self.mouse_click_info.mode=="log":

                self.log_pane.selection[1] = [ lineno, char_index ]
            
            elif self.mouse_click_info.mode=="log_double_click":
        
                s = self.log_pane.log.getLine(lineno)
            
                if [ lineno, char_index ] > self.log_pane.selection[0]:
                    right = min( ckit.wordbreak_TextFile( s, char_index+1, +1 ), len(s) )
                    self.log_pane.selection[0] = [ self.mouse_click_info.lineno, self.mouse_click_info.left ]
                    self.log_pane.selection[1] = [ lineno, right ]
                else:    
                    left = max( ckit.wordbreak_TextFile( s, char_index, -1 ), 0 )
                    self.log_pane.selection[0] = [ self.mouse_click_info.lineno, self.mouse_click_info.right ]
                    self.log_pane.selection[1] = [ lineno, left ]

            self.paint(PAINT_LOG)

    def _onMouseWheel( self, x, y, wheel, mod ):
        #print "_onMouseWheel", x, y, wheel

        if self.mouse_event_mask : return
        
        x, y = self.screenToClient( x, y )
        char_x, char_y, sub_x, sub_y, region, pane, pane_rect = self._mouseCommon( x, y, True )

        if region!=None and region&PAINT_UPPER:
        
            if pane.edit.visible:
                pane.edit.onMouseWheel( char_x, char_y, sub_x, sub_y, wheel, mod )
                self.mouse_click_info=None
            else:
                self.mouse_click_info=None
        
                while wheel>0:
                    self.command.ScrollUp()
                    self.command.ScrollUp()
                    self.command.ScrollUp()
                    wheel-=1
                while wheel<0:
                    self.command.ScrollDown()
                    self.command.ScrollDown()
                    self.command.ScrollDown()
                    wheel+=1

        elif region==PAINT_LOG:
            while wheel>0:
                self.command.LogUp()
                self.command.LogUp()
                self.command.LogUp()
                wheel-=1
            while wheel<0:
                self.command.LogDown()
                self.command.LogDown()
                self.command.LogDown()
                wheel+=1


    def _onCheckNetConnection( self, remote_resource_name ):
        
        def addConnection( hwnd, remote_resource_name ):
            try:
                cmailer_native.addConnection( hwnd, remote_resource_name )
            except Exception, e:
                print u"ERROR : 接続失敗 : %s" % remote_resource_name
                print e, "\n"
    
        self.synccall( addConnection, (self.getHWND(), remote_resource_name) )
            
    def leftPaneWidth(self):
        return self.width()

    def upperPaneHeight(self):
        return self.height() - self.log_window_height - 1

    def lowerPaneHeight(self):
        return self.log_window_height + 1

    def logPaneHeight(self):
        return self.log_window_height

    def fileListItemPaneHeight(self):
        return self.upperPaneHeight() - 3

    def leftPaneRect(self):
        return ( 0, 0, self.width(), self.height() - self.log_window_height - 1 )

    def logPaneRect(self):
        return ( 0, self.height()-self.log_window_height-1, self.width(), self.height()-1 )

    def activePaneRect(self):
        if self.focus==MainWindow.FOCUS_LEFT:
            return self.leftPaneRect()
        else:
            assert(False)

    def ratioToScreen( self, ratio ):
        rect = self.getWindowRect()
        return ( int(rect[0] * (1-ratio[0]) + rect[2] * ratio[0]), int(rect[1] * (1-ratio[1]) + rect[3] * ratio[1]) )

    ## メインウインドウの中心位置を、スクリーン座標系で返す
    #
    #  @return  ( X軸座標, Y軸座標 )
    #
    def centerOfWindowInPixel(self):
        rect = self.getWindowRect()
        return ( (rect[0]+rect[2])/2, (rect[1]+rect[3])/2 )

    def centerOfFocusedPaneInPixel(self):
        window_rect = self.getWindowRect()

        pane_rect = self.activePaneRect()

        if self.width()>0:
            x_ratio = float(pane_rect[0]+pane_rect[2])/2/self.width()
        else:
            x_ratio = 0.5
        if self.height()>0:
            y_ratio = float(pane_rect[1]+pane_rect[3])/2/self.height()
        else:
            y_ratio = 0.5

        return ( int(window_rect[0] * (1-x_ratio) + window_rect[2] * (x_ratio)), int(window_rect[1] * (1-y_ratio) + window_rect[3] * (y_ratio)) )

    def cursorPos(self):

        if self.focus==MainWindow.FOCUS_LEFT:
            pane = self.upper_pane
            pane_rect = self.leftPaneRect()
        else:
            assert(False)

        return ( pane_rect[0], pane_rect[1] + 2 + pane.cursor - pane.scroll_info.pos)

    def leftPane(self):
        return self.upper_pane

    def activePane(self):
        if self.focus==MainWindow.FOCUS_LEFT:
            return self.upper_pane
        else:
            assert(False)

    ## 左ペインの FileList オブジェクトを取得する
    def leftFileList(self):
        return self.upper_pane.file_list

    ## アクティブペインの FileList オブジェクトを取得する
    def activeFileList(self):
        if self.focus==MainWindow.FOCUS_LEFT:
            return self.upper_pane.file_list
        else:
            assert(False)

    def _items( self, pane ):
        items = []
        for i in xrange(pane.file_list.numItems()):
            item = pane.file_list.getItem(i)
            items.append(item)
        return items        

    ## 左ペインのアイテムのリストを取得する
    def leftItems(self):
        return self._items(self.upper_pane)

    ## アクティブペインのアイテムのリストを取得する
    def activeItems(self):
        if self.focus==MainWindow.FOCUS_LEFT:
            return self._items(self.upper_pane)
        else:
            assert(False)

    def _selectedItems( self, pane ):
        items = []
        for i in xrange(pane.file_list.numItems()):
            item = pane.file_list.getItem(i)
            if item.selected():
                items.append(item)
        return items        

    ## 左ペインの選択されているアイテムのリストを取得する
    def leftSelectedItems(self):
        return self._selectedItems(self.upper_pane)

    ## アクティブペインの選択されているアイテムのリストを取得する
    def activeSelectedItems(self):
        if self.focus==MainWindow.FOCUS_LEFT:
            return self._selectedItems(self.upper_pane)
        else:
            assert(False)

    def _cursorItem( self, pane ):
        return pane.file_list.getItem(pane.cursor)

    ## 左ペインのカーソル位置のアイテムを取得する
    def leftCursorItem(self):
        return self._cursorItem(self.upper_pane)

    ## アクティブペインのカーソル位置のアイテムを取得する
    def activeCursorItem(self):
        if self.focus==MainWindow.FOCUS_LEFT:
            return self._cursorItem(self.upper_pane)
        else:
            assert(False)

    def executeCommand( self, name, info ):

        #print "executeCommand", name

        if self.upper_pane.edit.visible:
            if self.upper_pane.edit.executeCommand( name, info ):
                return True

        try:
            command = getattr( self, "command_" + name )
        except AttributeError:
            return False

        command(info)
        return True

    def enumCommand(self):
        if self.upper_pane.edit.visible:
            for item in self.upper_pane.edit.enumCommand():
                yield item
        for attr in dir(self):
            if attr.startswith("command_"):
                yield attr[ len("command_") : ]

    ## 指定したペインのディレクトリを指定したリスト機能を使ってジャンプする
    def jumpLister( self, pane, lister, name=None, raise_error=False ):
        self.appendHistory(pane)
        try:
            self.subThreadCall( pane.file_list.setLister, (lister,), lister.cancel, raise_error=True )
            pane.file_list.applyItems()
        except:
            if raise_error : raise
            print u"ERROR : 移動失敗 : %s" % lister
            return
        pane.scroll_info = ckit.ScrollInfo()
        if name:
            pane.cursor = self.cursorFromName( pane.file_list, name )
        else:
            #pane.cursor = self.cursorFromHistory( pane.file_list, pane.history )
            pane.cursor = 0
        pane.scroll_info.makeVisible( pane.cursor, self.fileListItemPaneHeight(), 1 )
        if pane==self.upper_pane:
            self.paint(PAINT_LEFT)
        else:
            assert(False)
        self.appendHistory(pane)
    
    ## 指定したペインのディレクトリを指定したパスにジャンプする
    def jump( self, pane, path ):
        path = ckit.joinPath( pane.file_list.getLocation(), path )
        if os.path.isdir(path):
            dirname = path
            filename = u""
        else:
            dirname, filename = ckit.splitPath(path)
        lister = cmailer_email.lister_Folder(self.inbox_folder)
        self.jumpLister( pane, lister, filename )

    ## 左ペインのディレクトリを指定したパスにジャンプする
    def leftJump( self, path ):
        self.jump(self.upper_pane)

    ## アクティブペインのディレクトリを指定したパスにジャンプする
    def activeJump( self, path ):
        if self.focus==MainWindow.FOCUS_LEFT:
            self.jump(self.upper_pane,path)
        else:
            assert(False)

    ## 左ペインのディレクトリを指定したリスト機能を使ってジャンプする
    def leftJumpLister( self, lister, name=None, raise_error=False ):
        self.jumpLister( self.upper_pane, lister, name, raise_error )

    ## アクティブペインのディレクトリを指定したリスト機能を使ってジャンプする
    def activeJumpLister( self, lister, name=None, raise_error=False ):
        if self.focus==MainWindow.FOCUS_LEFT:
            self.jumpLister( self.upper_pane, lister, name, raise_error )
        else:
            assert(False)

    def refreshFileList( self, pane, manual, keep_selection ):
        name = pane.file_list.getItem(pane.cursor).name
        self.subThreadCall( pane.file_list.refresh, (manual,keep_selection) )
        pane.file_list.applyItems()
        pane.cursor = self.cursorFromName( pane.file_list, name )
        pane.scroll_info.makeVisible( pane.cursor, self.fileListItemPaneHeight(), 1 )

    def statusBar(self):
        return self.status_bar

    def _onStatusMessageTimedout(self):
        self.clearStatusMessage()

    ## ステータスバーにメッセージを表示する
    #
    #  @param self      -
    #  @param message   表示するメッセージ文字列
    #  @param timeout   表示時間 (ミリ秒単位)
    #  @param error     エラー形式(赤文字)で表示するか
    #
    #  CraftMailerのメインウインドウの下端にあるステータスバーに、任意の文字列を表示するための関数です。\n\n
    #
    #  引数 timeout に整数を指定すると、時間制限付の表示となり、自動的に消えます。\n
    #  引数 timeout に None を渡すと、時間制限のない表示となり、clearStatusMessage() が呼ばれるまで表示されたままになります。
    #
    #  @sa clearStatusMessage
    #
    def setStatusMessage( self, message, timeout=None, error=False ):

        self.status_bar_layer.setMessage(message,error)

        if not self.status_bar_resistered:
            self.status_bar.registerLayer(self.status_bar_layer)
            self.status_bar_resistered = True

        if timeout!=None:
            self.killTimer( self._onStatusMessageTimedout )
            self.setTimer( self._onStatusMessageTimedout, timeout )

        self.paint( PAINT_STATUS_BAR )

    ## ステータスバーのメッセージを消す
    #
    #  CraftMailerのステータスバーに表示されたメッセージを消します。
    #
    #  @sa setStatusMessage
    #
    def clearStatusMessage( self ):
        
        self.status_bar_layer.setMessage(u"")
        
        if self.status_bar_resistered:
            self.status_bar.unregisterLayer(self.status_bar_layer)
            self.status_bar_resistered = False
        
        self.killTimer(self._onStatusMessageTimedout)

        self.paint( PAINT_STATUS_BAR )

    def _onProgressTimedout(self):
        self.clearProgress()

    ## プログレスバーを表示する
    #
    #  @param self      -
    #  @param value     プログレス値 ( 0.0 ～ 1.0、または、[ 0.0 ～ 1.0, ... ] )
    #  @param timeout   表示時間 (ミリ秒単位)
    #
    #  CraftMailerのメインウインドウの右下の端にある領域に、プログレスバーを表示するか、すでに表示されているプログレスバーの進捗度を変更するための関数です。\n\n
    #
    #  引数 value には、進捗度合いを 0 から 1 までの浮動少数で渡します。\n
    #  通常は、引数 value には単一の浮動少数を渡しますが、二つ以上の進捗度を格納した配列を渡すことも可能で、その場合は複数のプログレスバーが縦に並んで表示されます。\n
    #  引数 value に None を渡したときは、[ビジーインジケータ] としての動作となり、プログレスバーが左右にアニメーションします。\n
    #
    #  引数 timeout に整数を指定すると、時間制限付の表示となり、自動的に消えます。\n
    #  引数 timeout に None を渡すと、時間制限のない表示となり、clearProgress() が呼ばれるまで表示されたままになります。
    #
    #  @sa clearProgress
    #
    def setProgressValue( self, value, timeout=None ):
        if self.progress_bar==None:
            self.progress_bar = ckit.ProgressBarWidget( self, self.width(), self.height()-1, 0, 0 )
        self.progress_bar.setValue(value)

        if timeout!=None:
            self.killTimer( self._onProgressTimedout )
            self.setTimer( self._onProgressTimedout, timeout )

        self.paint( PAINT_STATUS_BAR )

    ## プログレスバーを消す
    #
    #  CraftMailerのプログレスバーを消します。
    #
    #  @sa setProgressValue
    #
    def clearProgress( self ):
        if self.progress_bar:
            self.progress_bar.destroy()
            self.progress_bar = None
        self.paint( PAINT_STATUS_BAR )
        self.killTimer( self._onProgressTimedout )

    def appendHistory( self, pane, mark=False ):
        item = pane.file_list.getItem(pane.cursor)
        lister = pane.file_list.getLister()
        visible = isinstance( lister, cmailer_email.lister_Folder )
        #pane.history.append( pane.file_list.getLocation(), item.getName(), visible, mark )

    def cursorFromHistory( self, file_list, history ):
        history_item = history.find( file_list.getLocation() )
        if history_item==None : return 0
        cursor = file_list.indexOf( history_item[1] )
        if cursor<0 : return 0
        return cursor

    def cursorFromName( self, file_list, name ):
        cursor = file_list.indexOf( name )
        if cursor<0 : return 0
        return cursor

    def setItemFormat( self, itemformat ):
        self.itemformat = itemformat
        self.paint(PAINT_LEFT)

    #--------------------------------------------------------------------------

    def loadTheme(self):

        name = self.ini.get( "THEME", "name" )

        default_color = {
            "file_fg" : (255,255,255),
            "dir_fg" : (255,255,150),
            "hidden_file_fg" : (85,85,85),
            "hidden_dir_fg" : (85,85,50),
            "error_file_fg" : (255,0,0),
            "select_file_bg1" : (30,100,150),
            "select_file_bg2" : (60,200,255),
            "bookmark_file_bg2" : (100,70,0),
            "bookmark_file_bg1" : (140,110,0),
            "file_cursor" : (255,128,128),

            "choice_bg" : (50,50,50),
            "choice_fg" : (255,255,255),

            "diff_bg1" : (100,50,50),
            "diff_bg2" : (50,100,50),
            "diff_bg3" : (50,50,100),
        }

        ckit.setTheme( name, default_color )

        self.theme_enabled = False

    def reloadTheme(self):
        self.loadTheme()
        self.destroyThemePlane()
        self.createThemePlane()
        self.updateColor()
        self.updateWallpaper()

    def createThemePlane(self):

        self.plane_header = ckit.ThemePlane3x3( self, 'header.png' )
        self.plane_footer = ckit.ThemePlane3x3( self, 'footer.png' )
        self.plane_isearch = ckit.ThemePlane3x3( self, 'isearch.png', 1 )
        self.plane_statusbar = ckit.ThemePlane3x3( self, 'statusbar.png', 1.5 )
        self.plane_commandline = ckit.ThemePlane3x3( self, 'commandline.png', 1 )

        self.plane_isearch.show(False)
        self.plane_commandline.show(False)

        self.upper_pane.edit.createThemePlane()

        self.theme_enabled = True

        self.updatePaneRect()
        
    def destroyThemePlane(self):
        self.plane_header.destroy()
        self.plane_footer.destroy()
        self.plane_isearch.destroy()
        self.plane_statusbar.destroy()
        self.plane_commandline.destroy()

        self.upper_pane.edit.destroyThemePlane()

        self.theme_enabled = False

    def updatePaneRect(self):

        if 1:
            rect = self.leftPaneRect()

            x = rect[0]
            y = rect[1]
            width = rect[2]-rect[0]
            height = rect[3]-rect[1]

            self.upper_pane.edit.setPosSize( x, y+2, width, height-3 )

        if self.theme_enabled:

            client_rect = self.getClientRect()
            offset_x, offset_y = self.charToClient( 0, 0 )
            char_w, char_h = self.getCharSize()

            self.plane_header.setPosSize(                0,                                        1*char_h+offset_y,                                           client_rect[2],        char_h )
            self.plane_footer.setPosSize(                0,                                        (self.height()-self.log_window_height-2)*char_h+offset_y,    client_rect[2],        char_h )
            self.plane_statusbar.setPosSize(             0,                                        (self.height()-1)*char_h+offset_y,                           client_rect[2],        client_rect[3]-((self.height()-1)*char_h+offset_y) )

    #--------------------------------------------------------------------------

    def updateColor(self):
        ckit.TextWidget.updateColor()
        self.setBGColor( ckit.getColor("bg"))
        self.setCursorColor( ckit.getColor("cursor0"), ckit.getColor("cursor1") )
        if self.initialized:
            self.paint()

    #--------------------------------------------------------------------------
    
    def updateWallpaper(self):
        
        visible = self.ini.getint( "WALLPAPER", "visible" )
        strength = self.ini.getint( "WALLPAPER", "strength" )
        filename = unicode( self.ini.get( "WALLPAPER", "filename" ), "utf8" )
        
        def destroyWallpaper():
            if self.wallpaper:
                self.wallpaper.destroy()
                self.wallpaper = None
        
        if visible:

            if filename=="":
                cmailer_msgbox.popMessageBox( self, MessageBox.TYPE_OK, u"壁紙のエラー", u"Wallpaperコマンドを使って、壁紙ファイルを指定してください。" )
                destroyWallpaper()
                self.ini.set( "WALLPAPER", "visible", "0" )
                return
            
            destroyWallpaper()    
            self.wallpaper = cmailer_wallpaper.Wallpaper(self)
            try:
                self.wallpaper.load(filename,strength)
            except:
                print u"ERROR : 壁紙ファイルとして使用できない : %s" % filename
                destroyWallpaper()
                self.ini.set( "WALLPAPER", "visible", "0" )
                self.ini.set( "WALLPAPER", "filename", "" )
                return
                
            self.wallpaper.adjust()

        else:
            destroyWallpaper()

    #--------------------------------------------------------------------------

    def paint( self, option=PAINT_ALL ):

        if option & PAINT_FOCUSED:
            if option & PAINT_FOCUSED_LOCATION:
                option |= PAINT_LEFT_LOCATION
            if option & PAINT_FOCUSED_HEADER:
                option |= PAINT_LEFT_HEADER
            if option & PAINT_FOCUSED_ITEMS:
                option |= PAINT_LEFT_ITEMS
            if option & PAINT_FOCUSED_FOOTER:
                option |= PAINT_LEFT_FOOTER

        if option & PAINT_LEFT:
            if self.focus==MainWindow.FOCUS_LEFT:
                cursor = self.upper_pane.cursor
            else:
                cursor = None
            rect = self.leftPaneRect()

            x = rect[0]
            y = rect[1]
            width = rect[2]-rect[0]
            height = rect[3]-rect[1]

            if option & PAINT_LEFT_LOCATION and height>=1 :
                self._paintFileListLocation( x, y, width, 1, self.upper_pane.file_list )
            if option & PAINT_LEFT_HEADER and height>=2 :
                self._paintFileListHeaderInfo( x, y+1, width, 1, self.upper_pane.file_list )
            if option & PAINT_LEFT_ITEMS and height>=4 :
                if self.upper_pane.edit.visible:
                    self.upper_pane.edit.paint()
                else:
                    self._paintFileListItems( x, y+2, width, height-3, self.upper_pane.file_list, self.upper_pane.scroll_info, cursor )
            if option & PAINT_LEFT_FOOTER and height>=1 :
                if self.upper_pane.footer_paint_hook:
                    self.upper_pane.footer_paint_hook( x, y+height-1, width, 1, self.upper_pane.file_list )
                else:
                    self._paintFileListFooterInfo( x, y+height-1, width, 1, self.upper_pane.file_list )

        if option & PAINT_LOG:
            if self.logPaneHeight()>0:
                self._paintLog( 0, self.upperPaneHeight(), self.width(), self.logPaneHeight(), self.log_pane.log, self.log_pane.scroll_info, self.log_pane.selection )

        if option & PAINT_STATUS_BAR:
            if self.status_bar_paint_hook:
                if self.progress_bar:
                    self.progress_bar.show(False)
                self.status_bar_paint_hook( 0, self.height()-1, self.width(), 1 )
            else:
                if self.progress_bar:
                    progress_width = min( self.width() / 2, 20 )
                    self.progress_bar.setPosSize( self.width()-progress_width, self.height()-1, progress_width, 1 )
                    self.progress_bar.show(True)
                    self.progress_bar.paint()
                else:
                    progress_width = 0
                self.status_bar.paint( self, 0, self.height()-1, self.width()-progress_width, 1 )

    def _paintFileListLocation( self, x, y, width, height, file_list ):
        attr = ckit.Attribute( fg=ckit.getColor("fg"))
        s = ckit.adjustStringWidth( self, unicode(file_list), width, ckit.ALIGN_LEFT, ckit.ELLIPSIS_MID )
        self.putString( x, y, width, height, attr, u" " * width )
        self.putString( x, y, width, height, attr, s )

    def _paintFileListHeaderInfo( self, x, y, width, height, file_list ):
        attr = ckit.Attribute( fg=ckit.getColor("bar_fg"))
        self.putString( x, y, width, height, attr, u" " * width )
        self.putString( x+2, y, width-2, height, attr, file_list.getHeaderInfo() )

    def _paintFileListItems( self, x, y, width, height, file_list, scroll_info, cursor ):
        
        class UserData:
            pass
        userdata = UserData()
        
        attr = ckit.Attribute( fg=ckit.getColor("fg"))
        for i in xrange(height):
            index = scroll_info.pos+i
            if index < file_list.numItems():
                item = file_list.getItem(index)
                item.paint( self, x, y+i, width, cursor==index, self.itemformat, userdata )
            else:
                self.putString( x, y+i, width, 1, attr, u" " * width )

    def _paintFileListFooterInfo( self, x, y, width, height, file_list ):
        attr = ckit.Attribute( fg=ckit.getColor("bar_fg"))
        self.putString( x, y, width, height, attr, u" " * width )
        str_info = file_list.getFooterInfo()
        margin = max((width-len(str_info))/2,0)
        self.putString( x+margin, y, width-margin, height, attr, str_info )

    def _paintLog( self, x, y, width, height, log, scroll_info, selection ):

        attr = ckit.Attribute( fg=ckit.getColor("fg"))
        attr_selected = ckit.Attribute( fg=ckit.getColor("select_fg"), bg=ckit.getColor("select_bg"))

        selection_left, selection_right = selection 
        if selection_left > selection_right:
            selection_left, selection_right = selection_right, selection_left
        
        for i in xrange(height):

            if scroll_info.pos+i < log.numLines():
        
                if selection_left[0] <= scroll_info.pos+i <= selection_right[0]:
                
                    s = log.getLine( scroll_info.pos + i )
                
                    if selection_left[0]==scroll_info.pos+i:
                        left = selection_left[1]
                    else:
                        left = 0

                    if selection_right[0]==scroll_info.pos+i:
                        right = selection_right[1]
                    else:
                        right = len(s)
                
                    s = [ s[0:left], s[left:right], s[right:len(s)] ]
                
                    line_x = x

                    self.putString( line_x, y+i, width-line_x, 1, attr, s[0] )
                    line_x += self.getStringWidth(s[0])

                    self.putString( line_x, y+i, width-line_x, 1, attr_selected, s[1] )
                    line_x += self.getStringWidth(s[1])
                
                    self.putString( line_x, y+i, width-line_x, 1, attr, s[2] )
                    line_x += self.getStringWidth(s[2])

                    self.putString( line_x, y+i, width-line_x, 1, attr, u" " * (width-line_x) )
                
                else:
                    s = log.getLine( scroll_info.pos + i )
                    self.putString( x, y+i, width, 1, attr, s )
                    w = self.getStringWidth(s)
                    space_x = x + w
                    space_width = width - w
                    self.putString( space_x, y+i, space_width, 1, attr, u" " * space_width )
            else:
                self.putString( x, y+i, width, 1, attr, u" " * width )

    #--------------------------------------------------------------------------

    def registerStdio( self ):

        class Stdout:
            def write( writer_self, s ):
                self.log_pane.log.write(s)
                self.log_pane.scroll_info.makeVisible( self.log_pane.log.numLines()-1, self.logPaneHeight() )
                self.paint(PAINT_LOG)

        class Stderr:
            def write( writer_self, s ):
                self.log_pane.log.write(s)
                self.log_pane.scroll_info.makeVisible( self.log_pane.log.numLines()-1, self.logPaneHeight() )
                self.paint(PAINT_LOG)

        class DebugStdout:
            def write( writer_self, s ):
                if type(s)==type(u''):
                    s = s.encode("mbcs")
                sys.__stdout__.write(s)

        class DebugStderr:
            def write( writer_self, s ):
                if type(s)==type(u''):
                    s = s.encode("mbcs")
                sys.__stdout__.write(s)

        if self.debug:
            sys.stdout = DebugStdout()
            sys.stderr = DebugStderr()
        else:
            sys.stdout = Stdout()
            sys.stderr = Stderr()

    def unregisterStdio( self ):
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__

    ## 設定を読み込む
    #
    #  キーマップや jump_list などをリセットした上で、config,py を再読み込みします。
    #
    def configure( self ):

        default_keymap = self.ini.get( "MISC", "default_keymap" )

        ckit.Keymap.init()
        self.keymap = ckit.Keymap()
        self.keymap[ "Up" ] = self.command.CursorUp
        self.keymap[ "Down" ] = self.command.CursorDown
        self.keymap[ "C-Up" ] = self.command.CursorUpSelectedOrBookmark
        self.keymap[ "C-Down" ] = self.command.CursorDownSelectedOrBookmark
        self.keymap[ "PageUp" ] = self.command.CursorPageUp
        self.keymap[ "PageDown" ] = self.command.CursorPageDown
        self.keymap[ "C-PageUp" ] = self.command.CursorTop
        self.keymap[ "C-PageDown" ] = self.command.CursorBottom
        self.keymap[ "C-Tab" ] = self.command.ActivateCmailerNext
        self.keymap[ "A-Up" ] = self.command.MoveSeparatorUp
        self.keymap[ "A-Down" ] = self.command.MoveSeparatorDown
        self.keymap[ "C-A-Up" ] = self.command.MoveSeparatorUpQuick
        self.keymap[ "C-A-Down" ] = self.command.MoveSeparatorDownQuick
        self.keymap[ "Return" ] = self.command.Enter
        self.keymap[ "C-Return" ] = self.command.Execute
        self.keymap[ "Escape" ] = self.command.Escape
        self.keymap[ "S-Escape" ] = self.command.CancelTask
        self.keymap[ "End" ] = self.command.DeselectAll
        self.keymap[ "S-End" ] = self.command.Refresh
        self.keymap[ "S-Up" ] = self.command.LogUp
        self.keymap[ "S-Down" ] = self.command.LogDown
        self.keymap[ "S-Left" ] = self.command.LogPageUp
        self.keymap[ "S-Right" ] = self.command.LogPageDown
        self.keymap[ "Space" ] = self.command.SelectDown
        self.keymap[ "S-Space" ] = self.command.SelectUp
        self.keymap[ "C-Space" ] = self.command.SelectRegion
        self.keymap[ "A" ] = self.command.SelectAllFiles
        self.keymap[ "Home" ] = self.command.SelectAllFiles
        self.keymap[ "S-A" ] = self.command.SelectAll
        self.keymap[ "S-Home" ] = self.command.SelectAll
        self.keymap[ "E" ] = self.command.Edit
        self.keymap[ "F" ] = self.command.IncrementalSearch
        self.keymap[ "I" ] = self.command.Info
        self.keymap[ "H" ] = self.command.JumpHistory
        self.keymap[ "J" ] = self.command.JumpList
        self.keymap[ "S-J" ] = self.command.JumpInput
        self.keymap[ "C-J" ] = self.command.JumpFound
        self.keymap[ "Q" ] = self.command.Quit
        self.keymap[ "S" ] = self.command.SetSorter
        self.keymap[ "C-C" ] = self.command.SetClipboard_LogSelectedOrFilename
        self.keymap[ "C-S-C" ] = self.command.SetClipboard_Fullpath
        self.keymap[ "A-C" ] = self.command.SetClipboard_LogAll
        self.keymap[ "X" ] = self.command.CommandLine
        self.keymap[ "Z" ] = self.command.ConfigMenu
        self.keymap[ "S-Z" ] = self.command.ConfigMenu2
        self.keymap[ "S-Colon" ] = self.command.SetFilter
        self.keymap[ "Colon" ] = self.command.SetFilterList
        if default_keymap in ("101","106"):
            self.keymap[ "K" ] = self.command.Delete
            self.keymap[ "L" ] = self.command.View
        elif default_keymap in ("101afx","106afx"):
            self.keymap[ "D" ] = self.command.Delete
            self.keymap[ "V" ] = self.command.View
        if default_keymap in ("101","101afx"):
            self.keymap[ "Slash" ] = self.command.ContextMenu
            self.keymap[ "S-Slash" ] = self.command.ContextMenuDir
            self.keymap[ "Quote" ] = self.command.SelectUsingFilterList
            self.keymap[ "S-Quote" ] = self.command.SelectUsingFilter
        elif default_keymap in ("106","106afx"):
            self.keymap[ "BackSlash" ] = self.command.ContextMenu
            self.keymap[ "S-BackSlash" ] = self.command.ContextMenuDir
            self.keymap[ "Atmark" ] = self.command.SelectUsingFilterList
            self.keymap[ "S-Atmark" ] = self.command.SelectUsingFilter
        
        self.keymap[ "Left" ] = self.command.CursorLeft
        self.keymap[ "Right" ] = self.command.CursorRight
        self.keymap[ "C-Left" ] = self.command.CursorWordLeft
        self.keymap[ "C-Right" ] = self.command.CursorWordRight
        self.keymap[ "Home" ] = ckit.CommandSequence( self.command.CursorLineFirstGraph, self.command.CursorLineBegin )
        self.keymap[ "End" ] = self.command.CursorLineEnd
        self.keymap[ "Up" ] = self.command.CursorUp
        self.keymap[ "Down" ] = self.command.CursorDown
        self.keymap[ "PageUp" ] = self.command.CursorPageUp
        self.keymap[ "PageDown" ] = self.command.CursorPageDown
        self.keymap[ "A-Up" ] = self.command.SeekModifiedOrBookmarkPrev
        self.keymap[ "A-Down" ] = self.command.SeekModifiedOrBookmarkNext
        self.keymap[ "C-Home" ] = self.command.CursorDocumentBegin
        self.keymap[ "C-End" ] = self.command.CursorDocumentEnd
        self.keymap[ "C-B" ] = self.command.CursorCorrespondingBracket

        self.keymap[ "C-Up" ] = self.command.ScrollUp
        self.keymap[ "C-Down" ] = self.command.ScrollDown
        self.keymap[ "C-L" ] = self.command.ScrollCursorCenter

        self.keymap[ "S-Left" ] = self.command.SelectLeft
        self.keymap[ "S-Right" ] = self.command.SelectRight
        self.keymap[ "C-S-Left" ] = self.command.SelectWordLeft
        self.keymap[ "C-S-Right" ] = self.command.SelectWordRight
        self.keymap[ "S-Home" ] = self.command.SelectLineBegin
        self.keymap[ "S-End" ] = self.command.SelectLineEnd
        self.keymap[ "S-Up" ] = self.command.SelectUp
        self.keymap[ "S-Down" ] = self.command.SelectDown
        self.keymap[ "S-PageUp" ] = self.command.SelectPageUp
        self.keymap[ "S-PageDown" ] = self.command.SelectPageDown
        self.keymap[ "C-S-B" ] = self.command.SelectCorrespondingBracket
        self.keymap[ "C-S-Home" ] = self.command.SelectDocumentBegin
        self.keymap[ "C-S-End" ] = self.command.SelectDocumentEnd
        self.keymap[ "C-A" ] = self.command.SelectDocument

        self.keymap[ "C-S-Up" ] = self.command.SelectScrollUp
        self.keymap[ "C-S-Down" ] = self.command.SelectScrollDown

        self.keymap[ "Return" ] = ckit.CommandSequence( self.command.Enter, self.command.InsertReturnAutoIndent )
        self.keymap[ "Tab" ] = ckit.CommandSequence( self.command.IndentSelection, self.command.InsertTab )
        self.keymap[ "S-Tab" ] = ckit.CommandSequence( self.command.UnindentSelection, self.command.CursorTabLeft )
        self.keymap[ "Delete" ] = self.command.Delete
        self.keymap[ "Back" ] = self.command.DeleteCharLeft
        self.keymap[ "C-Delete" ] = self.command.DeleteWordRight
        self.keymap[ "C-Back" ] = self.command.DeleteWordLeft
        self.keymap[ "C-D" ] = self.command.DeleteCharRight
        self.keymap[ "C-H" ] = self.command.DeleteCharLeft
        self.keymap[ "C-K" ] = self.command.DeleteLineRight
        self.keymap[ "C-C" ] = self.command.Copy
        self.keymap[ "C-X" ] = self.command.Cut
        self.keymap[ "C-V" ] = self.command.Paste
        self.keymap[ "C-Z" ] = self.command.Undo
        self.keymap[ "C-Y" ] = self.command.Redo
        self.keymap[ "C-N" ] = self.command.SearchNext
        self.keymap[ "C-S-N" ] = self.command.SearchPrev
        self.keymap[ "C-Space" ] = self.command.CompleteAbbrev

        self.keymap[ "C-E" ] = self.command.ExtensionMenu
        self.keymap[ "C-M" ] = self.command.Bookmark1
        self.keymap[ "Escape" ] = ckit.CommandSequence( self.command.CloseList, self.command.FocusEdit, self.command.SelectCancel )

        self.jump_list = [
        ]

        self.filter_list = [
        ]

        self.select_filter_list = [
        ]

        self.sorter_list = [
            ( u"F : ファイル名",     cmailer_email.sorter_ByName(),       cmailer_email.sorter_ByName( order=-1 ) ),
            ( u"E : 拡張子",         cmailer_email.sorter_ByExt(),        cmailer_email.sorter_ByExt( order=-1 ) ),
            ( u"S : サイズ",         cmailer_email.sorter_BySize(),       cmailer_email.sorter_BySize( order=-1 ) ),
            ( u"T : タイムスタンプ", cmailer_email.sorter_ByTimeStamp(),  cmailer_email.sorter_ByTimeStamp( order=-1 ) ),
        ]

        self.association_list = [
        ]
        
        self.itemformat_list = [
            #( u"1 : 全て表示 : filename  .ext  99.9K YY/MM/DD HH:MM:SS",     cmailer_email.itemformat_Name_Ext_Size_YYMMDD_HHMMSS ),
            #( u"2 : 秒を省略 : filename  .ext  99.9K YY/MM/DD HH:MM",        cmailer_email.itemformat_Name_Ext_Size_YYMMDD_HHMM ),
            #( u"0 : 名前のみ : filename.ext",                                cmailer_email.itemformat_NameExt ),
        ]
        
        #self.itemformat = cmailer_email.itemformat_Name_Ext_Size_YYMMDD_HHMMSS

        self.commandline_list = [
            self.launcher,
            cmailer_commandline.commandline_Int32Hex(),
            cmailer_commandline.commandline_Calculator(),
        ]

        self.launcher.command_list = [
            ( u"Reload",           self.command.Reload ),
            ( u"About",            self.command.About ),
            ( u"Wallpaper",        self.command.Wallpaper ),
            ( u"Receive",          self.command.Receive ),
            ( u"_MemoryStat",      self.command.MemoryStat ),
            ( u"_RefererTree",     self.command.RefererTree ),
        ]
        
        ckit.reloadConfigScript( self.config_filename )
        ckit.callConfigFunc("configure",self)

        ckit.TextMode.staticconfigure(self)

        self.upper_pane.edit.configure()


    def loadState(self):

        try:
            fd = file( self.ini_filename, "rb" )
            msvcrt.locking( fd.fileno(), msvcrt.LK_LOCK, 1 )
            self.ini.readfp(fd)
            fd.close()
        except:
            pass
        
        ini_version = "0.00"
        try:
            ini_version = self.ini.get("GLOBAL","version")
        except:
            pass
        
        try:
            self.ini.add_section("GLOBAL")
        except ConfigParser.DuplicateSectionError:
            pass

        try:
            self.ini.add_section("GEOMETRY")
        except ConfigParser.DuplicateSectionError:
            pass

        try:
            self.ini.add_section("FONT")
        except ConfigParser.DuplicateSectionError:
            pass

        try:
            self.ini.add_section("THEME")
        except ConfigParser.DuplicateSectionError:
            pass

        try:
            self.ini.add_section("WALLPAPER")
        except ConfigParser.DuplicateSectionError:
            pass

        try:
            self.ini.add_section("HOTKEY")
        except ConfigParser.DuplicateSectionError:
            pass

        try:
            self.ini.add_section("LEFTPANE")
        except ConfigParser.DuplicateSectionError:
            pass

        try:
            self.ini.add_section("PATTERN")
        except ConfigParser.DuplicateSectionError:
            pass

        try:
            self.ini.add_section("SEARCH")
        except ConfigParser.DuplicateSectionError:
            pass

        try:
            self.ini.add_section("GREP")
        except ConfigParser.DuplicateSectionError:
            pass

        try:
            self.ini.add_section("BOOKMARK")
        except ConfigParser.DuplicateSectionError:
            pass

        try:
            self.ini.add_section("COMMANDLINE")
        except ConfigParser.DuplicateSectionError:
            pass

        try:
            self.ini.add_section("ACCOUNT")
        except ConfigParser.DuplicateSectionError:
            pass

        try:
            self.ini.add_section("MISC")
        except ConfigParser.DuplicateSectionError:
            pass

        try:
            self.ini.add_section("DEBUG")
        except ConfigParser.DuplicateSectionError:
            pass

        self.ini.set( "GLOBAL", "version", cmailer_resource.cmailer_version )

        if not self.ini.has_option( "GEOMETRY", "x" ):
            self.ini.set( "GEOMETRY", "x", str(0) )
        if not self.ini.has_option( "GEOMETRY", "y" ):
            self.ini.set( "GEOMETRY", "y", str(0) )
        if not self.ini.has_option( "GEOMETRY", "width" ):
            self.ini.set( "GEOMETRY", "width", str(80) )
        if not self.ini.has_option( "GEOMETRY", "height" ):
            self.ini.set( "GEOMETRY", "height", str(32) )
        if not self.ini.has_option( "GEOMETRY", "log_window_height" ):
            self.ini.set( "GEOMETRY", "log_window_height", str(10) )

        if not self.ini.has_option( "FONT", "name" ):
            self.ini.set( "FONT", "name", "" )
        if not self.ini.has_option( "FONT", "size" ):
            self.ini.set( "FONT", "size", "12" )

        if not self.ini.has_option( "THEME", "name" ):
            self.ini.set( "THEME", "name", "black" )

        if not self.ini.has_option( "WALLPAPER", "visible" ):
            self.ini.set( "WALLPAPER", "visible", "0" )
        if not self.ini.has_option( "WALLPAPER", "strength" ):
            self.ini.set( "WALLPAPER", "strength", "30" )
        if not self.ini.has_option( "WALLPAPER", "filename" ):
            self.ini.set( "WALLPAPER", "filename", "" )

        if not self.ini.has_option( "HOTKEY", "activate_vk" ):
            self.ini.set( "HOTKEY", "activate_vk", "0" )
        if not self.ini.has_option( "HOTKEY", "activate_mod" ):
            self.ini.set( "HOTKEY", "activate_mod", "0" )

        if not self.ini.has_option( "GREP", "pattern" ):
            self.ini.set( "GREP", "pattern", "" )
        if not self.ini.has_option( "GREP", "recursive" ):
            self.ini.set( "GREP", "recursive", str(1) )
        if not self.ini.has_option( "GREP", "regexp" ):
            self.ini.set( "GREP", "regexp", str(0) )
        if not self.ini.has_option( "GREP", "ignorecase" ):
            self.ini.set( "GREP", "ignorecase", str(1) )

        if not self.ini.has_option( "ACCOUNT", "server" ):
            self.ini.set( "ACCOUNT", "server", "" )
        if not self.ini.has_option( "ACCOUNT", "port" ):
            self.ini.set( "ACCOUNT", "port", "" )
        if not self.ini.has_option( "ACCOUNT", "username" ):
            self.ini.set( "ACCOUNT", "username", "" )
        if not self.ini.has_option( "ACCOUNT", "password" ):
            self.ini.set( "ACCOUNT", "password", "" )
        if not self.ini.has_option( "ACCOUNT", "lastid" ):
            self.ini.set( "ACCOUNT", "lastid", "0" )

        if not self.ini.has_option( "MISC", "locale" ):
            self.ini.set( "MISC", "locale", locale.getdefaultlocale()[0] )
        if not self.ini.has_option( "MISC", "default_keymap" ):
            self.ini.set( "MISC", "default_keymap", "106" )
        if not self.ini.has_option( "MISC", "esc_action" ):
            self.ini.set( "MISC", "esc_action", "none" )
        if not self.ini.has_option( "MISC", "isearch_type" ):
            self.ini.set( "MISC", "isearch_type", "strict" )
        if not self.ini.has_option( "MISC", "directory_separator" ):
            self.ini.set( "MISC", "directory_separator", "backslash" )
        if not self.ini.has_option( "MISC", "drive_case" ):
            self.ini.set( "MISC", "drive_case", "nocare" )
        if not self.ini.has_option( "MISC", "app_name" ):
            self.ini.set( "MISC", "app_name", u"CraftMailer".encode("utf8") )
        if not self.ini.has_option( "MISC", "delete_behavior" ):
            self.ini.set( "MISC", "delete_behavior", "builtin" )
        if not self.ini.has_option( "MISC", "ignore_1second" ):
            self.ini.set( "MISC", "ignore_1second", "1" )
        if not self.ini.has_option( "MISC", "confirm_copy" ):
            self.ini.set( "MISC", "confirm_copy", "1" )
        if not self.ini.has_option( "MISC", "confirm_move" ):
            self.ini.set( "MISC", "confirm_move", "1" )
        if not self.ini.has_option( "MISC", "confirm_extract" ):
            self.ini.set( "MISC", "confirm_extract", "1" )
        if not self.ini.has_option( "MISC", "confirm_quit" ):
            self.ini.set( "MISC", "confirm_quit", "1" )
        if not self.ini.has_option( "MISC", "walkaround_kb436093" ):
            self.ini.set( "MISC", "walkaround_kb436093", "0" )

        if not self.ini.has_option( "DEBUG", "detect_block" ):
            self.ini.set( "DEBUG", "detect_block", "0" )
        if not self.ini.has_option( "DEBUG", "print_errorinfo" ):
            self.ini.set( "DEBUG", "print_errorinfo", "0" )

        if self.ini.get( "MISC", "directory_separator" )=="slash":
            ckit.setPathSlash(True)
        else:
            ckit.setPathSlash(False)

        if self.ini.get( "MISC", "drive_case" )=="upper":
            ckit.setPathDriveUpper(True)
        elif self.ini.get( "MISC", "drive_case" )=="lower":
            ckit.setPathDriveUpper(False)
        else:    
            ckit.setPathDriveUpper(None)

        ckit.setGlobalOption( GLOBAL_OPTION_WALKAROUND_KB436093, int(self.ini.get( "MISC", "walkaround_kb436093" )) )

        cmailer_resource.cmailer_appname = unicode( self.ini.get( "MISC", "app_name" ), "utf8" )
        cmailer_resource.setLocale( self.ini.get( "MISC", "locale" ) )

    def saveState(self):

        print u"状態の保存"
        try:
            normal_rect = self.getNormalWindowRect()
            normal_size = self.getNormalSize()
            self.ini.set( "GEOMETRY", "x", str(normal_rect[0]) )
            self.ini.set( "GEOMETRY", "y", str(normal_rect[1]) )
            self.ini.set( "GEOMETRY", "width", str(normal_size[0]) )
            self.ini.set( "GEOMETRY", "height", str(normal_size[1]) )
            self.ini.set( "GEOMETRY", "log_window_height", str(self.log_window_height) )

            #self.upper_pane.history.save( self.ini, "LEFTPANE" )

            #self.bookmark.save( self.ini, "BOOKMARK" )

            self.commandline_history.save( self.ini, "COMMANDLINE" )
            #self.pattern_history.save( self.ini, "PATTERN" )
            #self.search_history.save( self.ini, "SEARCH" )
            
            tmp_ini_filename = self.ini_filename + ".tmp"

            fd = file( tmp_ini_filename, "w" )
            msvcrt.locking( fd.fileno(), msvcrt.LK_LOCK, 1 )
            self.ini.write(fd)
            fd.close()

            try:
                os.unlink( self.ini_filename )
            except OSError:
                pass    
            os.rename( tmp_ini_filename, self.ini_filename )

        except Exception, e:
            print u"失敗"
            print "  %s" % unicode(str(e),'mbcs')
        else:
            print u'完了'

    #--------------------------------------------------------------------------

    def startup(self):

        print cmailer_resource.startupString()

        self.jumpLister( self.upper_pane, cmailer_email.lister_Folder(self.inbox_folder) )

    #--------------------------------------------------------------------------

    def hotkey_Activate(self):
        # もっとも手前のcmailerをアクティブ化する
        desktop = pyauto.Window.getDesktop()
        wnd = desktop.getFirstChild()
        found = None
        while wnd:
            if wnd.getClassName()=="CmailerWindowClass":
                found = wnd
                break
            wnd = wnd.getNext()
        if found:
            wnd = found.getLastActivePopup()
            wnd.setForeground()

    def updateHotKey(self):

        activate_vk = self.ini.getint( "HOTKEY", "activate_vk" )
        activate_mod = self.ini.getint( "HOTKEY", "activate_mod" )

        self.killHotKey( self.hotkey_Activate )
        self.setHotKey( activate_vk, activate_mod, self.hotkey_Activate )

    #--------------------------------------------------------
    # ここから下のメソッドはキーに割り当てることができる
    #--------------------------------------------------------
    
    ## カーソルを1つ上に移動させる
    def command_CursorUp( self, info ):
        pane = self.activePane()
        pane.cursor -= 1
        if pane.cursor<0 : pane.cursor=0
        pane.scroll_info.makeVisible( pane.cursor, self.fileListItemPaneHeight(), 1 )
        self.paint(PAINT_FOCUSED_ITEMS)

    ## カーソルを1つ下に移動させる
    def command_CursorDown( self, info ):
        pane = self.activePane()
        pane.cursor += 1
        if pane.cursor>pane.file_list.numItems()-1 : pane.cursor=pane.file_list.numItems()-1
        pane.scroll_info.makeVisible( pane.cursor, self.fileListItemPaneHeight(), 1 )
        self.paint(PAINT_FOCUSED_ITEMS)

    ## 上方向の選択されているアイテムまでカーソルを移動させる
    def command_CursorUpSelected( self, info ):
        pane = self.activePane()
        cursor = pane.cursor
        while True:
            cursor -= 1
            if cursor<0 :
                cursor=0
                return
            if pane.file_list.getItem(cursor).selected():
                break
        pane.cursor = cursor
        pane.scroll_info.makeVisible( pane.cursor, self.fileListItemPaneHeight(), 1 )
        self.paint(PAINT_FOCUSED_ITEMS)

    ## 下方向の選択されているアイテムまでカーソルを移動させる
    def command_CursorDownSelected( self, info ):
        pane = self.activePane()
        cursor = pane.cursor
        while True:
            cursor += 1
            if cursor>pane.file_list.numItems()-1 :
                cursor=pane.file_list.numItems()-1
                return
            if pane.file_list.getItem(cursor).selected():
                break
        pane.cursor = cursor
        pane.scroll_info.makeVisible( pane.cursor, self.fileListItemPaneHeight(), 1 )
        self.paint(PAINT_FOCUSED_ITEMS)

    ## 上方向のブックマークされているアイテムまでカーソルを移動させる
    def command_CursorUpBookmark( self, info ):
        pane = self.activePane()
        cursor = pane.cursor
        while True:
            cursor -= 1
            if cursor<0 :
                cursor=0
                return
            if pane.file_list.getItem(cursor).bookmark():
                break
        pane.cursor = cursor
        pane.scroll_info.makeVisible( pane.cursor, self.fileListItemPaneHeight(), 1 )
        self.paint(PAINT_FOCUSED_ITEMS)

    ## 下方向のブックマークされているアイテムまでカーソルを移動させる
    def command_CursorDownBookmark( self, info ):
        pane = self.activePane()
        cursor = pane.cursor
        while True:
            cursor += 1
            if cursor>pane.file_list.numItems()-1 :
                cursor=pane.file_list.numItems()-1
                return
            if pane.file_list.getItem(cursor).bookmark():
                break
        pane.cursor = cursor
        pane.scroll_info.makeVisible( pane.cursor, self.fileListItemPaneHeight(), 1 )
        self.paint(PAINT_FOCUSED_ITEMS)

    ## 上方向の選択またはブックマークされているアイテムまでカーソルを移動させる
    def command_CursorUpSelectedOrBookmark( self, info ):
        pane = self.activePane()
        if pane.file_list.selected():
            self.command.CursorUpSelected()
        else:
            self.command.CursorUpBookmark()

    ## 下方向の選択またはブックマークされているアイテムまでカーソルを移動させる
    def command_CursorDownSelectedOrBookmark( self, info ):
        pane = self.activePane()
        if pane.file_list.selected():
            self.command.CursorDownSelected()
        else:
            self.command.CursorDownBookmark()

    ## 1ページ上方向にカーソルを移動させる
    def command_CursorPageUp( self, info ):
        pane = self.activePane()
        if pane.cursor>pane.scroll_info.pos + 1 :
            pane.cursor = pane.scroll_info.pos + 1
        else:
            pane.cursor -= self.fileListItemPaneHeight()
            if pane.cursor<0 : pane.cursor=0
            pane.scroll_info.makeVisible( pane.cursor, self.fileListItemPaneHeight(), 1 )
        self.paint(PAINT_FOCUSED_ITEMS)

    ## 1ページ下方向にカーソルを移動させる
    def command_CursorPageDown( self, info ):
        pane = self.activePane()
        if pane.cursor<pane.scroll_info.pos+self.fileListItemPaneHeight()-2:
            pane.cursor = pane.scroll_info.pos+self.fileListItemPaneHeight()-2
        else:
            pane.cursor += self.fileListItemPaneHeight()
        if pane.cursor>pane.file_list.numItems()-1 : pane.cursor=pane.file_list.numItems()-1
        pane.scroll_info.makeVisible( pane.cursor, self.fileListItemPaneHeight(), 1 )
        self.paint(PAINT_FOCUSED_ITEMS)

    ## リストの先頭にカーソルを移動させる
    def command_CursorTop( self, info ):
        pane = self.activePane()
        pane.cursor=0
        pane.scroll_info.makeVisible( pane.cursor, self.fileListItemPaneHeight(), 1 )
        self.paint(PAINT_FOCUSED_ITEMS)

    ## リストの末尾にカーソルを移動させる
    def command_CursorBottom( self, info ):
        pane = self.activePane()
        pane.cursor=pane.file_list.numItems()-1
        pane.scroll_info.makeVisible( pane.cursor, self.fileListItemPaneHeight(), 1 )
        self.paint(PAINT_FOCUSED_ITEMS)

    ## 一行上方向にスクロールする
    def command_ScrollUp( self, info ):
        pane = self.activePane()
        if pane.scroll_info.pos-1 >= 0:
            pane.scroll_info.pos -= 1
            pane.cursor -= 1
        self.paint(PAINT_FOCUSED_ITEMS)

    ## 一行下方向にスクロールする
    def command_ScrollDown( self, info ):
        pane = self.activePane()
        if pane.scroll_info.pos+1 < pane.file_list.numItems()-self.fileListItemPaneHeight()+2:
            pane.cursor += 1
            pane.scroll_info.pos += 1
        self.paint(PAINT_FOCUSED_ITEMS)

    ## カーソル位置のアイテムの選択状態を切り替える
    def command_Select( self, info ):
        pane = self.activePane()
        pane.file_list.selectItem(pane.cursor)
        self.paint( PAINT_FOCUSED_ITEMS | PAINT_FOCUSED_HEADER )

    ## カーソル位置のアイテムの選択状態を切り替えて、カーソルを1つ下に移動する
    def command_SelectDown( self, info ):
        self.command.Select()
        self.command.CursorDown()
        self.paint( PAINT_FOCUSED_ITEMS | PAINT_FOCUSED_HEADER )

    ## カーソル位置のアイテムの選択状態を切り替えて、カーソルを1つ上に移動する
    def command_SelectUp( self, info ):
        self.command.Select()
        self.command.CursorUp()
        self.paint( PAINT_FOCUSED_ITEMS | PAINT_FOCUSED_HEADER )

    ## 上方向の最も近い選択アイテムからカーソル位置までの全てのアイテムを選択する
    def command_SelectRegion( self, info ):
        pane = self.activePane()
        i = pane.cursor
        while i>=0:
            item = pane.file_list.getItem(i)
            if item.selected() :
                i+=1
                while i<=pane.cursor:
                    pane.file_list.selectItem(i)
                    self.paint( PAINT_FOCUSED_ITEMS | PAINT_FOCUSED_HEADER )
                    i+=1
                return
            i-=1

    ## ファイルリスト中の全てのアイテムの選択状態を切り替える
    def command_SelectAll( self, info ):
        pane = self.activePane()
        for i in xrange(pane.file_list.numItems()):
            pane.file_list.selectItem(i)
        self.paint( PAINT_FOCUSED_ITEMS | PAINT_FOCUSED_HEADER )

    ## ファイルリスト中の全てのファイルアイテムの選択状態を切り替える
    def command_SelectAllFiles( self, info ):
        pane = self.activePane()
        for i in xrange(pane.file_list.numItems()):
            item = pane.file_list.getItem(i)
            pane.file_list.selectItem(i)
        self.paint( PAINT_FOCUSED_ITEMS | PAINT_FOCUSED_HEADER )

    ## ファイルリスト中の全てのアイテムの選択を解除する
    def command_DeselectAll( self, info ):
        pane = self.activePane()
        for i in xrange(pane.file_list.numItems()):
            pane.file_list.selectItem( i, False )
        self.paint( PAINT_FOCUSED_ITEMS | PAINT_FOCUSED_HEADER )

    ## 上下のペインを分離するセパレータを上方向に動かす
    def command_MoveSeparatorUp( self, info ):

        log_window_height_old = self.log_window_height
        self.log_window_height += 3
        if self.log_window_height>self.height()-4 : self.log_window_height=self.height()-4
        
        self.log_pane.scroll_info.pos -= self.log_window_height-log_window_height_old
        if self.log_pane.scroll_info.pos>self.log_pane.log.numLines()-self.logPaneHeight() : self.log_pane.scroll_info.pos=self.log_pane.log.numLines()-self.logPaneHeight()
        if self.log_pane.scroll_info.pos<0 : self.log_pane.scroll_info.pos=0

        self.updatePaneRect()
        self.paint()

    ## 上下のペインを分離するセパレータを下方向に動かす
    def command_MoveSeparatorDown( self, info ):

        log_window_height_old = self.log_window_height
        self.log_window_height -= 3
        if self.log_window_height<0 : self.log_window_height=0

        self.log_pane.scroll_info.pos -= self.log_window_height-log_window_height_old
        if self.log_pane.scroll_info.pos>self.log_pane.log.numLines()-self.logPaneHeight() : self.log_pane.scroll_info.pos=self.log_pane.log.numLines()-self.logPaneHeight()
        if self.log_pane.scroll_info.pos<0 : self.log_pane.scroll_info.pos=0

        self.updatePaneRect()
        self.paint()

    ## 上下のペインを分離するセパレータを上方向に高速に動かす
    #
    #  縦3分割した位置に達するまで、セパレータを上方向に動かします。
    #
    def command_MoveSeparatorUpQuick( self, info ):
        
        pos_list = [
            (self.height()-4) * 1 / 3,
            (self.height()-4) * 2 / 3,
            (self.height()-4) * 3 / 3,
            ]
        
        for pos in pos_list:
            if pos > self.log_window_height : break

        log_window_height_old = self.log_window_height
        self.log_window_height = pos
        
        self.log_pane.scroll_info.pos -= self.log_window_height-log_window_height_old
        if self.log_pane.scroll_info.pos>self.log_pane.log.numLines()-self.logPaneHeight() : self.log_pane.scroll_info.pos=self.log_pane.log.numLines()-self.logPaneHeight()
        if self.log_pane.scroll_info.pos<0 : self.log_pane.scroll_info.pos=0

        self.updatePaneRect()
        self.paint()

    ## 上下のペインを分離するセパレータを下方向に高速に動かす
    #
    #  縦3分割した位置に達するまで、セパレータを下方向に動かします。
    #
    def command_MoveSeparatorDownQuick( self, info ):

        pos_list = [
            (self.height()-4) * 3 / 3,
            (self.height()-4) * 2 / 3,
            (self.height()-4) * 1 / 3,
            0,
            ]
        
        for pos in pos_list:
            if pos < self.log_window_height : break

        log_window_height_old = self.log_window_height
        self.log_window_height = pos

        self.log_pane.scroll_info.pos -= self.log_window_height-log_window_height_old
        if self.log_pane.scroll_info.pos>self.log_pane.log.numLines()-self.logPaneHeight() : self.log_pane.scroll_info.pos=self.log_pane.log.numLines()-self.logPaneHeight()
        if self.log_pane.scroll_info.pos<0 : self.log_pane.scroll_info.pos=0

        self.updatePaneRect()
        self.paint()

    ## カーソル位置のアイテムに対して、メーラ内で関連付けられたデフォルトの動作を実行する
    #
    #  以下の順番で処理されます。
    #
    #  -# enter_hook があればそれを呼び出し、enter_hookがTrueを返したら処理を終了。
    #  -# ショートカットファイルであれば、リンク先のファイルを扱う。
    #  -# アイテムがディレクトリであれば、そのディレクトリの中に移動。
    #  -# association_list に一致する関連付けがあれば、それを実行。
    #  -# アーカイブファイルであれば、仮想ディレクトリの中に移動。
    #  -# 画像ファイルであれば、画像ビューアを起動。
    #  -# 音楽ファイルであれば、内蔵ミュージックプレイヤで再生。
    #  -# それ以外のファイルは、テキストビューアまたはバイナリビューアで閲覧。
    #
    def command_Enter( self, info ):

        if self.enter_hook:
            if self.enter_hook():
                return True

        pane = self.activePane()
        item = pane.file_list.getItem(pane.cursor)

        ext = os.path.splitext(item.name)[1].lower()

        for association in self.association_list:
            for pattern in association[0].split():
                if fnmatch.fnmatch( item.name, pattern ):
                    association[1](item)
                    return

        else:
            self._viewCommon(item)


    ## カーソル位置のアイテムに対して、OSで関連付けられた処理を実行する
    def command_Execute( self, info ):
        pane = self.activePane()
        item = pane.file_list.getItem(pane.cursor)
        fullpath = os.path.join( pane.file_list.getLocation(), item.name )
        self.appendHistory( pane, True )
        self.subThreadCall( ckit.shellExecute, ( None, None, fullpath.replace('/','\\'), u"", pane.file_list.getLocation().replace('/','\\') ) )

    ## ESCキー相当の処理を実行する
    #
    #  ESCキーの動作は、設定メニュー2で変更することが出来ます。
    #
    def command_Escape( self, info ):
        esc_action = self.ini.get( "MISC", "esc_action" )
        if esc_action == "inactivate":
            self.inactivate()

    ## バックグラウンドタスクを全てキャンセルする
    def command_CancelTask( self, info ):
        for task_queue in self.task_queue_stack:
            task_queue.cancel()

    ## アクティブペインのファイルリストを再読み込みする
    def command_Refresh( self, info ):
        self.refreshFileList( self.activePane(), True, False )
        self.paint(PAINT_FOCUSED)

    ## ログペインを1行上方向にスクロールする
    def command_LogUp( self, info ):
        self.log_pane.scroll_info.pos -= 1
        if self.log_pane.scroll_info.pos<0 : self.log_pane.scroll_info.pos=0
        self.paint( PAINT_LOG )

    ## ログペインを1行下方向にスクロールする
    def command_LogDown( self, info ):
        self.log_pane.scroll_info.pos += 1
        if self.log_pane.scroll_info.pos>self.log_pane.log.numLines()-self.logPaneHeight() : self.log_pane.scroll_info.pos=self.log_pane.log.numLines()-self.logPaneHeight()
        if self.log_pane.scroll_info.pos<0 : self.log_pane.scroll_info.pos=0
        self.paint( PAINT_LOG )

    ## ログペインを1ページ上方向にスクロールする
    def command_LogPageUp( self, info ):
        self.log_pane.scroll_info.pos -= self.logPaneHeight()
        if self.log_pane.scroll_info.pos<0 : self.log_pane.scroll_info.pos=0
        self.paint( PAINT_LOG )

    ## ログペインを1ページ下方向にスクロールする
    def command_LogPageDown( self, info ):
        self.log_pane.scroll_info.pos += self.logPaneHeight()
        if self.log_pane.scroll_info.pos>self.log_pane.log.numLines()-self.logPaneHeight() : self.log_pane.scroll_info.pos=self.log_pane.log.numLines()-self.logPaneHeight()
        if self.log_pane.scroll_info.pos<0 : self.log_pane.scroll_info.pos=0
        self.paint( PAINT_LOG )

    ## 選択されているアイテムを削除する(デフォルトの方法で)
    #
    #  CraftMailerでは、メーラに内蔵された削除機能と、OSのゴミ箱を使った削除を選択することができます。
    #  command_Delete ではデフォルトに設定された方法で削除を実行します。
    #  削除のデフォルト動作は、設定メニュー2で変更することが出来ます。
    #
    def command_Delete( self, info ):

        pane = self.activePane()
        item_filter = pane.file_list.getFilter()

        items = []
        
        for i in xrange(pane.file_list.numItems()):
            item = pane.file_list.getItem(i)
            if item.selected() and hasattr(item,"delete"):
                items.append(item)

        if len(items):

            result = cmailer_msgbox.popMessageBox( self, MessageBox.TYPE_YESNO, u"削除の確認", u"削除しますか？" )
            if result!=MessageBox.RESULT_YES : return

            def deselectItem(item):
                for i in xrange(pane.file_list.numItems()):
                    if pane.file_list.getItem(i) is item:
                        pane.file_list.selectItem(i,False)
                        if pane == self.upper_pane:
                            region = PAINT_LEFT
                        self.paint(region)
                        return

            def jobDelete( job_item ):
                
                # ビジーインジケータ On
                self.setProgressValue(None)
                
                used_folder_set = set()
                
                for item in items:
                
                    def schedule():
                        if job_item.isCanceled():
                            return True
                        if job_item.waitPaused():
                            self.setProgressValue(None)
                
                    if schedule(): break
                
                    item.delete( used_folder_set, schedule, sys.stdout.write )
                    if not job_item.isCanceled():
                        deselectItem(item)
                
                print used_folder_set
                
                for folder in used_folder_set:
                    folder.flush()

            def jobDeleteFinished( job_item ):

                # ビジーインジケータ Off
                self.clearProgress()

                if job_item.isCanceled():
                    print u'中断しました.\n'
                else:
                    print "Done.\n"
                    
                self.refreshFileList( self.upper_pane, True, True )
                self.paint(PAINT_LEFT)

            self.appendHistory( pane, True )

            job_item = ckit.JobItem( jobDelete, jobDeleteFinished )
            self.taskEnqueue( job_item, u"削除" )


    ## 選択されているアイテムをエディタで編集する
    #
    #  editor が呼び出し可能オブジェクトであれば、それを呼び出します。
    #  その際、引数には ( ファイルアイテムオブジェクト, (行番号,カラム), カレントディレクトリ ) が渡ります。
    #  editor が呼び出し可能オブジェクトでなければ、テキストエディタのプログラムファイル名とみなし、shellExecute を使ってエディタを起動します。
    #
    def command_Edit( self, info ):
        
        pane = self.activePane()
        items = []
        
        def appendItem(item):
            items.append(item)
        
        for i in xrange(pane.file_list.numItems()):
            item = pane.file_list.getItem(i)
            if item.selected():
                appendItem(item)

        if len(items)==0:
            item = pane.file_list.getItem(pane.cursor)
            appendItem(item)

        if len(items)<=0 : return

        def editItems():
            pass

        self.appendHistory( pane, True )

        self.subThreadCall( editItems, () )

    ## ジャンプリストを表示しジャンプする
    #
    #  jump_list に登録されたジャンプ先をリスト表示します。\n
    #  jump_list は、( 表示名, ジャンプ先のパス ) という形式のタプルが登録されているリストです。
    #
    def command_JumpList( self, info ):

        pane = self.activePane()

        pos = self.centerOfFocusedPaneInPixel()
        list_window = cmailer_listwindow.ListWindow( pos[0], pos[1], 5, 1, self.width()-5, self.height()-3, self, self.ini, u"ジャンプ", self.jump_list, initial_select=0 )
        self.enable(False)
        list_window.messageLoop()
        result = list_window.getResult()
        self.enable(True)
        self.activate()
        list_window.destroy()

        if result<0 : return

        newdirname = self.jump_list[result][1]
        
        if type(newdirname)!=unicode:
            print u"ERROR : ファイルパスはUNICODE形式である必要があります."
            return

        self.jumpLister( pane, cmailer_email.lister_Folder(self.inbox_folder) )

    ## 履歴リストを表示しジャンプする
    def command_JumpHistory( self, info ):

        upper_pane = self.upper_pane

        pane = self.activePane()

        def onKeyDown( vk, mod ):

            if vk==VK_DELETE and mod==0:
                select = list_window.getResult()
                pane.history.remove( items[select][0] )
                del items[select]
                list_window.remove(select)
                return True

        list_window = None

        while True:

            title = u"履歴"

            # ちらつきを防止するために ListWindow の破棄を遅延する
            list_window_old = list_window

            items = filter( lambda item : item[2], pane.history.items )
            list_items = map( lambda item : cmailer_listwindow.ListItem( item[0], item[3] ), items )
            
            def onStatusMessage( width, select ):
                return u""

            pos = self.centerOfWindowInPixel()
            list_window = cmailer_listwindow.ListWindow( pos[0], pos[1], 5, 1, self.width()-5, self.height()-3, self, self.ini, title, list_items, initial_select=0, onekey_search=False, keydown_hook=onKeyDown, statusbar_handler=onStatusMessage )

            if list_window_old:
                list_window_old.destroy()

            self.enable(False)
            list_window.messageLoop()
            result = list_window.getResult()
            self.enable(True)

        self.activate()
        list_window.destroy()

        if result<0 : return

        newdirname = items[result][0]

        pane = self.activePane()

        self.jumpLister( pane, cmailer_email.lister_Folder(self.inbox_folder) )

    ## パスを入力しジャンプする
    def command_JumpInput( self, info ):
        pane = self.activePane()

        fixed_candidate_items = filter( lambda item : item[2], pane.history.items )
        fixed_candidate_items = map( lambda item : item[0], fixed_candidate_items )

        def statusString_IsExists( update_info ):
            path = ckit.joinPath( pane.file_list.getLocation(), update_info.text )
            if update_info.text and os.path.exists(path):
                return u"OK"
            else:
                return u"  "

        result = self.commandLine( u"Jump", auto_complete=False, autofix_list=["\\/","."], candidate_handler=cmailer_misc.candidate_Filename( pane.file_list.getLocation(), fixed_candidate_items ), status_handler=statusString_IsExists )
        if result==None : return

        path = ckit.joinPath( pane.file_list.getLocation(), result )
        if os.path.isdir(path):
            dirname = path
            filename = u""
        else:
            dirname, filename = ckit.splitPath(path)

        self.jumpLister( pane, cmailer_email.lister_Folder(self.inbox_folder), filename )

    ## SearchやGrepの検索結果リストを表示しジャンプする
    def command_JumpFound( self, info ):

        upper_pane = self.upper_pane

        pane = self.activePane()

        def onKeyDown( vk, mod ):
            pass

        list_window = None

        while True:

            title = u"検索結果"

            # ちらつきを防止するために ListWindow の破棄を遅延する
            list_window_old = list_window

            list_items = map( lambda item : ckit.normPath(item.getName()), pane.found_items )
            
            def onStatusMessage( width, select ):
                return u""

            pos = self.centerOfWindowInPixel()
            list_window = cmailer_listwindow.ListWindow( pos[0], pos[1], 16, 1, self.width()-5, self.height()-3, self, self.ini, title, list_items, initial_select=0, onekey_search=False, return_modkey=True, keydown_hook=onKeyDown, statusbar_handler=onStatusMessage )

            if list_window_old:
                list_window_old.destroy()

            self.enable(False)
            list_window.messageLoop()
            result, mod = list_window.getResult()
            self.enable(True)

        self.activate()
        list_window.destroy()

        if result<0 : return
        if not list_items : return

        # Shift-Enter で決定したときは、ファイルリストに反映させる
        if mod==MODKEY_SHIFT:
            new_lister = cmailer_email.lister_Custom( self, pane.found_prefix, pane.found_location, pane.found_items )
            pane.file_list.setLister( new_lister )
            pane.file_list.applyItems()
            pane.scroll_info = ckit.ScrollInfo()
            pane.cursor = self.cursorFromName( pane.file_list, list_items[result] )
            pane.scroll_info.makeVisible( pane.cursor, self.fileListItemPaneHeight(), 1 )
            self.paint(PAINT_FOCUSED)

        else:
            path = list_items[result]

            if os.path.isdir(path):
                dirname = path
                filename = u""
            else:
                dirname, filename = ckit.splitPath(path)

            self.jumpLister( pane, cmailer_email.lister_Folder(self.inbox_folder), filename )

    ## インクリメンタルサーチを行う
    def command_IncrementalSearch( self, info ):

        pane = self.activePane()

        isearch = cmailer_isearch.IncrementalSearch( self.ini )

        def updateStatusBar():
            if isearch.migemo_re_result:
                s = ckit.adjustStringWidth( self, isearch.migemo_re_result.group(0), self.width()-2, ckit.ALIGN_LEFT, ckit.ELLIPSIS_MID )
                migemo_status_bar_layer.setMessage( s, error=False )
            else:
                migemo_status_bar_layer.setMessage( u"", error=False )
            self.paint(PAINT_STATUS_BAR)

        def getString(i):
            item = pane.file_list.getItem(i)
            return item.name

        def cursorUp():
            pane.cursor = isearch.cursorUp( getString, pane.file_list.numItems(), pane.cursor, pane.scroll_info.pos, self.fileListItemPaneHeight(), 1 )
            pane.scroll_info.makeVisible( pane.cursor, self.fileListItemPaneHeight(), 1 )
            self.paint(PAINT_FOCUSED_ITEMS)
            updateStatusBar()

        def cursorDown():
            pane.cursor = isearch.cursorDown( getString, pane.file_list.numItems(), pane.cursor, pane.scroll_info.pos, self.fileListItemPaneHeight(), 1 )
            pane.scroll_info.makeVisible( pane.cursor, self.fileListItemPaneHeight(), 1 )
            self.paint(PAINT_FOCUSED_ITEMS)
            updateStatusBar()

        def cursorPageUp():
            pane.cursor = isearch.cursorPageUp( getString, pane.file_list.numItems(), pane.cursor, pane.scroll_info.pos, self.fileListItemPaneHeight(), 1 )
            pane.scroll_info.makeVisible( pane.cursor, self.fileListItemPaneHeight(), 1 )
            self.paint(PAINT_FOCUSED_ITEMS)
            updateStatusBar()

        def cursorPageDown():
            pane.cursor = isearch.cursorPageDown( getString, pane.file_list.numItems(), pane.cursor, pane.scroll_info.pos, self.fileListItemPaneHeight(), 1 )
            pane.scroll_info.makeVisible( pane.cursor, self.fileListItemPaneHeight(), 1 )
            self.paint(PAINT_FOCUSED_ITEMS)
            updateStatusBar()

        def onKeyDown( vk, mod ):

            if vk==VK_RETURN:
                self.quit()
            elif vk==VK_ESCAPE:
                self.quit()
            elif vk==VK_SPACE:
                if mod==0:
                    self.command.Select()
                    cursorDown()
                elif mod==MODKEY_SHIFT:
                    self.command.Select()
                    cursorUp()
            elif vk==VK_UP:
                cursorUp()
            elif vk==VK_DOWN:
                cursorDown()
            elif vk==VK_PRIOR:
                cursorPageUp()
            elif vk==VK_NEXT:
                cursorPageDown()

            return True

        def onChar( ch, mod ):

            if ch==ord('\b'):
                newvalue = isearch.isearch_value[:-1]
            elif ch==ord(' '):
                return
            else:
                newvalue = isearch.isearch_value + unichr(ch)

            accept = False

            item = pane.file_list.getItem( pane.cursor )
            if isearch.fnmatch(item.name,newvalue):
                accept = True
            else:
                
                if isearch.isearch_type=="inaccurate":
                    isearch_type_list = [ "strict", "partial", "inaccurate" ]
                else:
                    isearch_type_list = [ "strict", "partial", "migemo" ]
                
                last_type_index = isearch_type_list.index(isearch.isearch_type)
                for isearch_type_index in xrange(last_type_index+1):
                    for i in xrange( pane.file_list.numItems() ):
                        item = pane.file_list.getItem(i)
                        if isearch.fnmatch(item.name,newvalue,isearch_type_list[isearch_type_index]):
                            pane.cursor = i
                            pane.scroll_info.makeVisible( pane.cursor, self.fileListItemPaneHeight(), 1 )
                            accept = True
                            break
                    if accept: break

            if accept:
                isearch.isearch_value = newvalue
                self.paint(PAINT_FOCUSED_ITEMS | PAINT_FOCUSED_FOOTER)

            updateStatusBar()

            return True

        def paint( x, y, width, height, file_list ):

            if self.theme_enabled:

                pos1 = self.charToClient( x, y )
                char_w, char_h = self.getCharSize()

                self.plane_isearch.setPosSize( pos1[0]-char_w/2, pos1[1], width*char_w+char_w, char_h )

            s = u" Search : %s_" % ( isearch.isearch_value )
            s = ckit.adjustStringWidth(self,s,width-1)

            attr = ckit.Attribute( fg=ckit.getColor("fg"))
            self.putString( x, y, width-1, y, attr, s )

        keydown_hook_old = self.keydown_hook
        char_hook_old = self.char_hook
        mouse_event_mask_old = self.mouse_event_mask
        footer_paint_hook_old = pane.footer_paint_hook

        # ステータスバーレイヤの登録
        migemo_status_bar_layer = cmailer_statusbar.SimpleStatusBarLayer(-2)
        self.status_bar.registerLayer(migemo_status_bar_layer)
        self.paint(PAINT_STATUS_BAR)

        self.keydown_hook = onKeyDown
        self.char_hook = onChar
        self.mouse_event_mask = True
        pane.footer_paint_hook = paint
        if self.theme_enabled:
            self.plane_isearch.show(True)

        self.paint(PAINT_FOCUSED_ITEMS | PAINT_FOCUSED_FOOTER)

        self.removeKeyMessage()
        self.messageLoop()

        # ステータスバーレイヤの解除
        self.status_bar.unregisterLayer(migemo_status_bar_layer)
        self.paint(PAINT_STATUS_BAR)
        
        self.keydown_hook = keydown_hook_old
        self.char_hook = char_hook_old
        self.mouse_event_mask = mouse_event_mask_old
        pane.footer_paint_hook = footer_paint_hook_old
        if self.theme_enabled:
            self.plane_isearch.show(False)

        self.paint(PAINT_FOCUSED_ITEMS | PAINT_FOCUSED_FOOTER)


    ## 選択アイテムの統計情報を出力する
    def command_Info( self, info ):

        pane = self.activePane()
        location = pane.file_list.getLocation()
        item_filter = pane.file_list.getFilter()

        items = []
        for i in xrange(pane.file_list.numItems()):
            item = pane.file_list.getItem(i)
            if item.selected():
                items.append(item)

        # ファイルが選択されていないときは、カーソル位置のファイルの詳細情報を出力する
        if len(items)==0 :

            item = pane.file_list.getItem(pane.cursor)
            
            if not item.name : return
            
            name_lines = ckit.splitLines( self, item.name, self.width()-11 )
            print u"名前     : %s" % name_lines[0]
            for i in xrange(1,len(name_lines)):
                print u"           %s" % name_lines[i]
            
            print u"サイズ   : %s (%d bytes)" % ( cmailer_misc.getFileSizeString(item.size()), item.size() )

            t = item.time()
            print u"更新日時 : %04d/%02d/%02d %02d:%02d:%02d" % ( t[0]%10000, t[1], t[2], t[3], t[4], t[5] )

            print u""

            self.appendHistory( pane, True )

            return

        def jobInfo( job_item ):

            print u'統計情報 :'

            # ビジーインジケータ On
            self.setProgressValue(None)

            # 最長のディレクトリ名を調べる
            max_dirname_len = 12

            class Stat:
                def __init__(self):
                    self.num_files = 0
                    self.num_dirs = 0
                    self.total_size = 0
            
            files_stat = Stat()
            total_stat = Stat()
            
            def printStat( name, stat ):
                print " %s%s%s %7d FILEs %7d DIRs %12d bytes %7s" % ( name, ' '*(max_dirname_len-self.getStringWidth(name)), " : ", stat.num_files, stat.num_dirs, stat.total_size, cmailer_misc.getFileSizeString(stat.total_size) )

            def printLine():
                print '-'*(max_dirname_len+59)
            
            printLine()

            for item in items:
            
                if job_item.isCanceled(): break
                
                if job_item.waitPaused():
                    self.setProgressValue(None)

                total_stat.num_files += 1
                files_stat.num_files += 1

                total_stat.total_size += item.size()
                files_stat.total_size += item.size()
                    
            if job_item.isCanceled():
                print u'中断しました.\n'
            else:
                
                if files_stat.num_files or files_stat.num_dirs:
                    printStat( u"直接マーク分", files_stat )
                printLine()
                printStat( u"合計", total_stat )
                print ''
            
                print u'Done.\n'


        def jobInfoFinished( job_item ):

            # ビジーインジケータ Off
            self.clearProgress()

        self.appendHistory( pane, True )

        job_item = ckit.JobItem( jobInfo, jobInfoFinished )
        self.taskEnqueue( job_item, u"Info" )

    ## ワイルドカードを入力し、フィルタを設定する
    def command_SetFilter( self, info ):
        pane = self.activePane()

        result = self.commandLine( u"Filter", candidate_handler=self.pattern_history.candidateHandler, candidate_remove_handler=self.pattern_history.candidateRemoveHandler )
        if result==None : return
        
        self.pattern_history.append(result)

        self.subThreadCall( pane.file_list.setFilter, (cmailer_email.filter_Default( result, dir_policy=True ),) )
        pane.file_list.applyItems()
        pane.scroll_info = ckit.ScrollInfo()
        pane.cursor = self.cursorFromHistory( pane.file_list, pane.history )
        pane.scroll_info.makeVisible( pane.cursor, self.fileListItemPaneHeight(), 1 )
        self.paint(PAINT_FOCUSED)

    ## フィルタリストを表示し、フィルタを設定する
    def command_SetFilterList( self, info ):
        pane = self.activePane()

        pos = self.centerOfFocusedPaneInPixel()
        list_window = cmailer_listwindow.ListWindow( pos[0], pos[1], 5, 1, self.width()-5, self.height()-3, self, self.ini, u"パターン", self.filter_list, 0 )
        self.enable(False)
        list_window.messageLoop()
        result = list_window.getResult()
        self.enable(True)
        self.activate()
        list_window.destroy()

        if result<0 : return

        self.subThreadCall( pane.file_list.setFilter, (self.filter_list[result][1],) )
        pane.file_list.applyItems()
        pane.scroll_info = ckit.ScrollInfo()
        pane.cursor = self.cursorFromHistory( pane.file_list, pane.history )
        pane.scroll_info.makeVisible( pane.cursor, self.fileListItemPaneHeight(), 1 )
        self.paint(PAINT_FOCUSED)

    ## ワイルドカードを入力し、合致するファイルを選択する
    def command_SelectUsingFilter( self, info ):
        pane = self.activePane()

        result = self.commandLine( u"Select", candidate_handler=self.pattern_history.candidateHandler, candidate_remove_handler=self.pattern_history.candidateRemoveHandler )
        if result==None : return

        self.pattern_history.append(result)

        file_filter = cmailer_email.filter_Default( result, dir_policy=None )
        for i in xrange(pane.file_list.numItems()):
            item = pane.file_list.getItem(i)
            if file_filter(item):
                pane.file_list.selectItem( i, True )

        self.paint( PAINT_FOCUSED_ITEMS | PAINT_FOCUSED_HEADER )

    ## フィルタリストを表示し、合致するファイルを選択する
    def command_SelectUsingFilterList( self, info ):
        pane = self.activePane()

        pos = self.centerOfFocusedPaneInPixel()
        list_window = cmailer_listwindow.ListWindow( pos[0], pos[1], 5, 1, self.width()-5, self.height()-3, self, self.ini, u"パターン選択", self.select_filter_list, 0 )
        self.enable(False)
        list_window.messageLoop()
        result = list_window.getResult()
        self.enable(True)
        self.activate()
        list_window.destroy()

        if result<0 : return

        file_filter = self.select_filter_list[result][1]
        for i in xrange(pane.file_list.numItems()):
            item = pane.file_list.getItem(i)
            if file_filter(item):
                pane.file_list.selectItem( i, True )

        self.paint( PAINT_FOCUSED_ITEMS | PAINT_FOCUSED_HEADER )

    ## ソートポリシーを設定する
    def command_SetSorter( self, info ):
        pane = self.activePane()

        initial_select = 0
        for i in xrange(len(self.sorter_list)):
            sorter = self.sorter_list[i]
            if id(pane.file_list.getSorter()) in ( id(sorter[1]), id(sorter[2]) ):
                initial_select = i

        self.setStatusMessage( u"Shiftを押しながら決定 : 降順" )

        pos = self.centerOfFocusedPaneInPixel()
        list_window = cmailer_listwindow.ListWindow( pos[0], pos[1], 5, 1, self.width()-5, self.height()-3, self, self.ini, u"ソート", self.sorter_list, initial_select=initial_select, onekey_decide=True, return_modkey=True )
        self.enable(False)
        list_window.messageLoop()
        result, mod = list_window.getResult()
        self.enable(True)
        self.activate()
        list_window.destroy()
        
        self.clearStatusMessage()

        if result<0 : return
        
        if mod==MODKEY_SHIFT:
            sorter = self.sorter_list[result][2]
        else:
            sorter = self.sorter_list[result][1]

        # カーソル位置保存
        self.appendHistory(pane)

        self.subThreadCall( pane.file_list.setSorter, (sorter,) )
        pane.file_list.applyItems()
        pane.scroll_info = ckit.ScrollInfo()
        pane.cursor = self.cursorFromHistory( pane.file_list, pane.history )
        pane.scroll_info.makeVisible( pane.cursor, self.fileListItemPaneHeight(), 1 )
        self.paint(PAINT_FOCUSED_ITEMS)


    ## コンテキストメニューをポップアップする
    def command_ContextMenu( self, info ):
        pane = self.activePane()

        if not hasattr( pane.file_list.getLister(), "popupContextMenu" ):
            return

        items = []
        for i in xrange(pane.file_list.numItems()):
            item = pane.file_list.getItem(i)
            if item.selected():
                items.append(item)

        if len(items)==0:
            items.append(pane.file_list.getItem(pane.cursor))

        cursor_pos = self.cursorPos()

        pos = self.charToScreen( cursor_pos[0], cursor_pos[1]+1 )

        self.removeKeyMessage()
        result = pane.file_list.getLister().popupContextMenu( self, pos[0], pos[1], items )
        
        if result:
            self.appendHistory( pane, True )

        self.paint(PAINT_FOCUSED)

    ## カレントディレクトリに対してコンテキストメニューをポップアップする
    def command_ContextMenuDir( self, info ):
        pane = self.activePane()

        if not hasattr( pane.file_list.getLister(), "popupContextMenu" ):
            return

        pane_rect = self.activePaneRect()

        pos = self.charToScreen( pane_rect[0]+1, pane_rect[1]+1 )

        self.removeKeyMessage()
        result = pane.file_list.getLister().popupContextMenu( self, pos[0], pos[1] )

        if result:
            self.appendHistory( pane, True )

        self.paint(PAINT_FOCUSED)

    ## メーラを終了する
    def command_Quit( self, info ):

        if self.ini.getint("MISC","confirm_quit"):
            result = cmailer_msgbox.popMessageBox( self, MessageBox.TYPE_YESNO, u"終了確認", u"%sを終了しますか？" % cmailer_resource.cmailer_appname )
            if result!=MessageBox.RESULT_YES : return

        self.quit()

    def _viewCommon( self, item ):
        if hasattr(item,"openBody"):
            fd = item.openBody()
            s = fd.read()
            
            print s

            edit = self.upper_pane.edit
            begin = edit.pointDocumentBegin()
            end = edit.pointDocumentEnd()
            edit.modifyText( begin, end, s, append_undo=False, ignore_readonly=True )
            edit.show(True)
            edit.enableCursor(True)

            self.paint(PAINT_LEFT)

    ## テキストビューアまたはバイナリビューアでファイルを閲覧する
    def command_View( self, info ):
        pane = self.activePane()
        item = pane.file_list.getItem(pane.cursor)
        self._viewCommon( item )

    ## ログペインの選択範囲またはアイテムのファイル名をクリップボードにコピーする
    #
    #  ログペインのテキストが選択されている場合は、その選択範囲をクリップボードに格納します。
    #  ログペインのテキストが選択されていない場合は、アイテムのファイル名をクリップボードに格納します。
    #
    def command_SetClipboard_LogSelectedOrFilename( self, info ):
        selection_left, selection_right = self.log_pane.selection
        if selection_left != selection_right:
            self.command.SetClipboard_LogSelected()
        else:
            self.command.SetClipboard_Filename()

    ## アイテムのファイル名をクリップボードにコピーする
    #
    #  アイテムが選択されているときは、選択されている全てのアイテムのファイル名を、改行区切りで連結してクリップボードに格納します。
    #  アイテムが選択されていないときは、カーソル位置のファイル名をクリップボードに格納します。
    #
    def command_SetClipboard_Filename( self, info ):
        pane = self.activePane()
        filename_list = []
        for i in xrange(pane.file_list.numItems()):
            item = pane.file_list.getItem(i)
            if item.selected():
                filename_list.append( item.name )

        if len(filename_list)==0:
            item = pane.file_list.getItem(pane.cursor)
            filename_list.append( item.name )

        ckit.setClipboardText( '\r\n'.join(filename_list) )

        self.command.DeselectAll()

        self.setStatusMessage( u"ファイル名をクリップボードにコピーしました", 3000 )

    ## アイテムのファイル名をフルパスでクリップボードにコピーする
    #
    #  アイテムが選択されているときは、選択されている全てのアイテムのフルパスを、改行区切りで連結してクリップボードに格納します。
    #  アイテムが選択されていないときは、カーソル位置のファイルのフルパスをクリップボードに格納します。
    #
    def command_SetClipboard_Fullpath( self, info ):
        pane = self.activePane()
        filename_list = []
        for i in xrange(pane.file_list.numItems()):
            item = pane.file_list.getItem(i)
            if item.selected():
                filename_list.append( ckit.normPath(unicode(item)) )

        if len(filename_list)==0:
            item = pane.file_list.getItem(pane.cursor)
            filename_list.append( ckit.normPath(unicode(item)) )

        ckit.setClipboardText( '\r\n'.join(filename_list) )

        self.command.DeselectAll()

        self.setStatusMessage( u"フルパスをクリップボードにコピーしました", 3000 )

    ## ログペインの選択範囲をクリップボードにコピーする
    def command_SetClipboard_LogSelected( self, info ):

        joint_text = u""
        
        selection_left, selection_right = self.log_pane.selection 
        if selection_left > selection_right:
            selection_left, selection_right = selection_right, selection_left

        i = selection_left[0]
        while i<=selection_right[0] and i<self.log_pane.log.numLines():
        
            s = self.log_pane.log.getLine(i)

            if i==selection_left[0]:
                left = selection_left[1]
            else:
                left = 0

            if i==selection_right[0]:
                right = selection_right[1]
            else:
                right = len(s)
            
            joint_text += s[left:right]
            
            if i!=selection_right[0]:
                joint_text += "\r\n"
            
            i += 1
        
        if joint_text:
            ckit.setClipboardText(joint_text)

        self.log_pane.selection = [ [ 0, 0 ], [ 0, 0 ] ]
        self.paint(PAINT_LOG)

        self.setStatusMessage( u"ログをクリップボードにコピーしました", 3000 )

    ## ログペイン全域をクリップボードにコピーする
    def command_SetClipboard_LogAll( self, info ):
        lines = []
        for i in xrange(self.log_pane.log.numLines()):
            lines.append( self.log_pane.log.getLine(i) )
        ckit.setClipboardText( '\r\n'.join(lines) )

        self.log_pane.selection = [ [ 0, 0 ], [ 0, 0 ] ]
        self.paint(PAINT_LOG)

        self.setStatusMessage( u"全てのログをクリップボードにコピーしました", 3000 )

    def command_Receive( self, info ):

        def jobReceive(job_item):

            print "Receive begin"

            self.inbox_folder.lock()

            # ビジーインジケータ On
            self.setProgressValue(None)

            try:
                for email in self.account.receive():
                    #print email.subject, time.strftime( "%Y/%m/%d %H:%M:%S", email.date )
                    self.inbox_folder.add(email)
                self.inbox_folder.flush()
            finally:

                # ビジーインジケータ Off
                self.clearProgress()

                self.inbox_folder.unlock()

            print "Receive end"

        def jobReceiveFinished(job_item):
            self.refreshFileList( self.activePane(), True, True )
            self.paint(PAINT_FOCUSED)

        job_item = ckit.JobItem( jobReceive, jobReceiveFinished )
        self.taskEnqueue( job_item, u"Receive" )


    ## Pythonインタプリタのメモリの統計情報を出力する(デバッグ目的)
    def command_MemoryStat( self, info ):
        
        print u'メモリ統計情報 :'

        gc.collect()
        objs = gc.get_objects()
        stat = {}
        
        for obj in objs:
        
            str_type = str(type(obj))
            if str_type.find("'instance'")>=0:
                str_type += " " + str(obj.__class__)
            
            try:
                stat[str_type] += 1
            except KeyError:
                stat[str_type] = 1

        keys = stat.keys()
        keys.sort()

        # 最長の名前を調べる
        max_len = 10
        for k in keys:
            k_len = self.getStringWidth(k)
            if max_len < k_len:
                max_len = k_len

        for k in keys:
            print "  %s%s : %d" % ( k, ' '*(max_len-self.getStringWidth(k)), stat[k] )
        print u''

        print u'Done.\n'


    ## ファイルがオープンされっぱなしになっているバグを調査するためのコマンド(デバッグ目的)
    #
    #  引数には、( クラス名, 探索の最大の深さ ) を渡します。
    #
    #  ex) RefererTree;ZipInfo;5
    #
    def command_RefererTree( self, info ):
    
        kwd = info.args[0]
    
        max_depth = 5
        if len(info.args)>1:
            max_depth = int(info.args[1])
    
        known_id_table = {}
        
        gc.collect()
        objs = gc.get_objects()
        
        def isRelatedObject(obj):
            if type(obj).__name__ == kwd:
                return True
            if type(obj).__name__ == 'instance':
                if obj.__class__.__name__ == kwd:
                    return True
            return False            
            
        
        def dumpReferer(obj,depth):
            
            if known_id_table.has_key(id(obj)):
                return
            known_id_table[id(obj)] = True
            
            str_type = str(type(obj))
            
            if str_type.find("'instance'")>=0:
                str_type += " " + str(obj.__class__)
            print "   " * depth, str_type

            if depth==max_depth: return

            referers = gc.get_referrers(obj)
            for referer in tuple(referers):
                dumpReferer(referer,depth+1)
            
        
        print "---- referer --------"
        
        for obj in tuple(objs):
            if isRelatedObject(obj):
                dumpReferer(obj,0)

        print "-----------------------------"

    ## コマンドラインにコマンドを入力する
    def command_CommandLine( self, info ):

        def _getHint( update_info ):

            left = update_info.text[ : update_info.selection[0] ]
            left_lower = left.lower()
            pos_arg = left.rfind(";")+1
            arg = left[ pos_arg : ]
            pos_dir = max( arg.rfind("/")+1, arg.rfind("\\")+1 )
            
            return left_lower, pos_arg, pos_dir

        def onCandidate( update_info ):
        
            left_lower, pos_arg, pos_dir = _getHint(update_info)

            candidate_list = []
            candidate_map = {}

            for item in self.commandline_history.items:
                item_lower = item.lower()
                if item_lower.startswith(left_lower) and len(item_lower)!=len(left_lower):
                    right = item[ pos_arg + pos_dir: ]
                    candidate_list.append(right)
                    candidate_map[right] = None

            for commandline_function in self.commandline_list:
                for candidate in commandline_function.onCandidate( update_info ):
                    if not candidate_map.has_key(candidate):
                        candidate_list.append(candidate)
                        candidate_map[candidate] = None

            return candidate_list, pos_arg + pos_dir

        def onCandidateRemove(text):
            try:
                self.commandline_history.remove(text)
                return True
            except KeyError:
                pass
            return False        

        def statusString( update_info ):
            if update_info.text:
                for commandline_function in self.commandline_list:
                    s = commandline_function.onStatusString(update_info.text)
                    if s!=None:
                        return s
            return u"  "

        def onEnter( commandline, text, mod ):
            for commandline_function in self.commandline_list:
                if commandline_function.onEnter( commandline, text, mod ):
                    break
            return True

        self.commandLine( u"Command", auto_complete=False, autofix_list=["\\/",".",";"], candidate_handler=onCandidate, candidate_remove_handler=onCandidateRemove, status_handler=statusString, enter_handler=onEnter )
        
    ## カーソル位置の画像ファイルを壁紙にする
    def command_Wallpaper( self, info ):
        item = self.activeCursorItem()
        if hasattr(item,"getFullpath"):
            fullpath = item.getFullpath()
            self.ini.set( "WALLPAPER", "visible", "1" )
            self.ini.set( "WALLPAPER", "filename", fullpath.encode("utf8") )
            self.updateWallpaper()
        else:
            print u"ERROR : 壁紙に設定できないアイテム : %s" % item.getName()

    ## 設定メニュー1をポップアップする
    #
    #  設定メニュー1には、普段の使用で、頻繁に変更する可能性が高いものが入っています。
    #
    def command_ConfigMenu( self, info ):
        cmailer_configmenu.doConfigMenu( self )

    ## 設定メニュー2をポップアップする
    #
    #  設定メニュー2には、普段の使用で、頻繁には変更しないものが入っています。
    #
    def command_ConfigMenu2( self, info ):
        cmailer_configmenu.doConfigMenu2( self )

    ## 設定スクリプトをリロードする
    def command_Reload( self, info ):
        self.configure()
        print u"設定スクリプトをリロードしました.\n"

    ## メーラのバージョン情報を出力する
    def command_About( self, info ):
        print cmailer_resource.startupString()

#--------------------------------------------------------------------

## @} mainwindow
