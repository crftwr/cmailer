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
import StringIO

import pyauto

import ckit
from ckit.ckit_const import *

"""
import cmailer_isearch
import cmailer_listwindow
import cmailer_grepwindow
import cmailer_textviewer
import cmailer_configmenu
import cmailer_wallpaper
import cmailer_misc
import cmailer_native
"""

import cmailer_email
import cmailer_resource
import cmailer_msgbox
import cmailer_statusbar
import cmailer_usernamespace
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

PAINT_RIGHT_LOCATION     = 1<<4
PAINT_RIGHT_HEADER       = 1<<5
PAINT_RIGHT_ITEMS        = 1<<6
PAINT_RIGHT_FOOTER       = 1<<7

PAINT_FOCUSED_LOCATION   = 1<<8
PAINT_FOCUSED_HEADER     = 1<<9
PAINT_FOCUSED_ITEMS      = 1<<10
PAINT_FOCUSED_FOOTER     = 1<<11

PAINT_VERTICAL_SEPARATOR = 1<<12
PAINT_LOG                = 1<<13
PAINT_STATUS_BAR         = 1<<14

PAINT_LEFT               = PAINT_LEFT_LOCATION | PAINT_LEFT_HEADER | PAINT_LEFT_ITEMS | PAINT_LEFT_FOOTER
PAINT_RIGHT              = PAINT_RIGHT_LOCATION | PAINT_RIGHT_HEADER | PAINT_RIGHT_ITEMS | PAINT_RIGHT_FOOTER
PAINT_FOCUSED            = PAINT_FOCUSED_LOCATION | PAINT_FOCUSED_HEADER | PAINT_FOCUSED_ITEMS | PAINT_FOCUSED_FOOTER
PAINT_UPPER              = PAINT_LEFT | PAINT_RIGHT | PAINT_VERTICAL_SEPARATOR
PAINT_ALL                = PAINT_LEFT | PAINT_RIGHT | PAINT_VERTICAL_SEPARATOR | PAINT_LOG | PAINT_STATUS_BAR

## メーラのメインウインドウ
#
#  メーラの主な機能を実現しているクラスです。\n\n
#  設定ファイル config.py の configure に渡される window 引数は、MainWindow クラスのオブジェクトです。
#
class MainWindow( ckit.Window ):

    FOCUS_LEFT  = 0
    FOCUS_RIGHT = 1

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

        if self.ini.getint( "DEBUG", "detect_block" ):
            cmailer_debug.enableBlockDetector()

        if self.ini.getint( "DEBUG", "print_errorinfo" ):
            cmailer_debug.enablePrintErrorInfo()

        self.setCursorPos( -1, -1 )

        self.updateHotKey()

        self.focus = MainWindow.FOCUS_LEFT
        self.left_window_width = self.ini.getint( "GEOMETRY", "left_window_width" )
        self.log_window_height = self.ini.getint( "GEOMETRY", "log_window_height" )

        self.show_hidden = False

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
            cmailer_email.Pop3Receiver(
                    "pop.gmail.com", 995,
                    self.ini.get( "ACCOUNT", "username" ), self.ini.get( "ACCOUNT", "password" )
            ),
            None
        )

        class Pane:
            pass

        self.left_pane = Pane()
        """
        self.left_pane.history = History()
        self.left_pane.history.load( self.ini, "LEFTPANE" )
        self.left_pane.found_prefix = u""
        self.left_pane.found_location = u""
        self.left_pane.found_items = []
        self.left_pane.file_list = cmailer_filelist.FileList( self, cmailer_filelist.lister_Empty() )
        self.left_pane.scroll_info = ckit.ScrollInfo()
        self.left_pane.cursor = 0
        self.left_pane.footer_paint_hook = None
        """

        self.right_pane = Pane()
        """
        self.right_pane.history = History()
        self.right_pane.history.load( self.ini, "RIGHTPANE" )
        self.right_pane.found_prefix = u""
        self.right_pane.found_location = u""
        self.right_pane.found_items = []
        self.right_pane.file_list = cmailer_filelist.FileList( self, cmailer_filelist.lister_Empty() )
        self.right_pane.scroll_info = ckit.ScrollInfo()
        self.right_pane.cursor = 0
        self.right_pane.footer_paint_hook = None
        """

        self.log_pane = Pane()
        self.log_pane.log = Log()
        self.log_pane.scroll_info = ckit.ScrollInfo()
        self.log_pane.selection = [ [ 0, 0 ], [ 0, 0 ] ]

        self.keymap = ckit.Keymap()
        """
        self.jump_list = []
        self.filter_list = []
        self.select_filter_list = []
        self.compare_list = []
        self.compare_tool_list = []
        self.sorter_list = []
        self.association_list = []
        self.itemformat_list = []
        self.itemformat = cmailer_filelist.itemformat_Name_Ext_Size_YYMMDD_HHMMSS
        self.editor = u"notepad.exe"
        self.diff_editor = None
        self.commandline_list = []
        """
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
        #self.left_pane.file_list.destroy()
        #self.right_pane.file_list.destroy()
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

    def onTimerAutoRefresh(self):
    
        if len(self.task_queue_stack)>0 : return

        if not self.acquireUserInputOwnership(False) : return
        try:
            if self.left_pane.file_list.isChanged():
                self.refreshFileList( self.left_pane, True, True )
                self.paint(PAINT_LEFT)
            if self.right_pane.file_list.isChanged():
                self.refreshFileList( self.right_pane, True, True )
                self.paint(PAINT_RIGHT)
        finally:
            self.releaseUserInputOwnership()


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
        self.updateThemePosSize()

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
        
        if self.left_window_width>width-1 : self.left_window_width=width-1
        if self.log_window_height>height-4 : self.log_window_height=height-4
        if self.log_window_height<0 : self.log_window_height=0
        self.left_pane.scroll_info.makeVisible( self.left_pane.cursor, self.fileListItemPaneHeight(), 1 )
        self.right_pane.scroll_info.makeVisible( self.right_pane.cursor, self.fileListItemPaneHeight(), 1 )

        self.updateThemePosSize()
        
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
        """
        if pane.file_list.selected():
            selected = 1
        """

        try:
            func = self.keymap.table[ ckit.KeyEvent(vk,mod,extra=selected) ]
        except KeyError:
            return

        if not self.acquireUserInputOwnership(False) : return
        try:
            if self.profile:
                cProfile.runctx( "func()", globals(), locals() )
            else:
                func()
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
        
        left_pane_rect = list( self.leftPaneRect() )
        right_pane_rect = list( self.rightPaneRect() )
        log_pane_rect = list( self.logPaneRect() )

        region = None
        pane = None
        pane_rect = None

        if left_pane_rect[0]<=char_x<left_pane_rect[2] and left_pane_rect[1]<=char_y<left_pane_rect[3]:

            if focus : self.command_FocusLeft()

            if left_pane_rect[1]==char_y:
                region = PAINT_LEFT_LOCATION
                pane = self.left_pane
                pane_rect = [ left_pane_rect[0], left_pane_rect[1], left_pane_rect[2], left_pane_rect[1]+1 ]
            elif left_pane_rect[1]+2<=char_y<left_pane_rect[3]-1:
                region = PAINT_LEFT_ITEMS
                pane = self.left_pane
                pane_rect = [ left_pane_rect[0], left_pane_rect[1]+2, left_pane_rect[2], left_pane_rect[3]-1 ]

        elif right_pane_rect[0]<=char_x<right_pane_rect[2] and right_pane_rect[1]<=char_y<right_pane_rect[3]:

            if focus : self.command_FocusRight()

            if left_pane_rect[1]==char_y:
                region = PAINT_RIGHT_LOCATION
                pane = self.right_pane
                pane_rect = [ right_pane_rect[0], right_pane_rect[1], right_pane_rect[2], right_pane_rect[1]+1 ]
            elif left_pane_rect[1]+2<=char_y<left_pane_rect[3]-1:
                region = PAINT_RIGHT_ITEMS
                pane = self.right_pane
                pane_rect = [ right_pane_rect[0], right_pane_rect[1]+2, right_pane_rect[2], right_pane_rect[3]-1 ]

        elif log_pane_rect[0]<=char_x<log_pane_rect[2] and log_pane_rect[1]<=char_y<log_pane_rect[3]:
            region = PAINT_LOG
            pane = self.log_pane
            pane_rect = log_pane_rect

        return [ char_x, char_y, region, pane, pane_rect ]

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

        char_x, char_y, region, pane, pane_rect = self._mouseCommon( x, y, True )

        if region==PAINT_LEFT_ITEMS or region==PAINT_RIGHT_ITEMS:

            if self.ini.getint( "MISC", "mouse_operation" ):

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
            item_index = char_y-pane_rect[1]+pane.scroll_info.pos
            if item_index<pane.file_list.numItems():
                for i in xrange(pane.file_list.numItems()):
                    item = pane.file_list.getItem(i)
                    if item.selected():
                        if hasattr(item,"getFullpath"):
                            dnd_items.append( os.path.normpath(item.getFullpath()) )

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
        
        if self.mouse_click_info.mode=="item":

            x, y, mod = self.mouse_click_info.x, self.mouse_click_info.y, self.mouse_click_info.mod
            self.mouse_click_info = None

            char_x, char_y, region, pane, pane_rect = self._mouseCommon( x, y, True )

            if region==PAINT_LEFT_ITEMS or region==PAINT_RIGHT_ITEMS:

                if self.ini.getint( "MISC", "mouse_operation" ):
        
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

        char_x, char_y, region, pane, pane_rect = self._mouseCommon( x, y, True )

        if region==PAINT_LEFT_ITEMS or region==PAINT_RIGHT_ITEMS:

            if self.ini.getint( "MISC", "mouse_operation" ):

                item_index = char_y-pane_rect[1]+pane.scroll_info.pos
                if item_index<pane.file_list.numItems():
                    pane.cursor = item_index
                    self.command_Enter()

        elif region==PAINT_LEFT_LOCATION or region==PAINT_RIGHT_LOCATION:

            if self.ini.getint( "MISC", "mouse_operation" ):
                self.command_GotoParentDir()
        
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

        char_x, char_y, region, pane, pane_rect = self._mouseCommon( x, y, True )

    def _onMiddleButtonUp( self, x, y, mod ):
        #print "_onMiddleButtonUp", x, y

        if self.mouse_event_mask : return

        self.mouse_click_info = None

    def _onRightButtonDown( self, x, y, mod ):
        #print "_onRightButtonDown", x, y

        if self.mouse_event_mask : return

        self.mouse_click_info=None

        char_x, char_y, region, pane, pane_rect = self._mouseCommon( x, y, True )

        if region==PAINT_LEFT_ITEMS or region==PAINT_RIGHT_ITEMS:

            if self.ini.getint( "MISC", "mouse_operation" ):

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

        elif region==PAINT_LEFT_LOCATION or region==PAINT_RIGHT_LOCATION:
            self.mouse_click_info = MouseInfo( "item", x=x, y=y, mod=mod, dnd_items=[] )


    def _onRightButtonUp( self, x, y, mod ):
        #print "_onRightButtonUp", x, y

        if self.mouse_event_mask : return

        if self.mouse_click_info==None : return
        if self.mouse_click_info.mode!="item" :
            self.mouse_click_info=None
            return
        x, y, mod = self.mouse_click_info.x, self.mouse_click_info.y, self.mouse_click_info.mod
        self.mouse_click_info = None

        char_x, char_y, region, pane, pane_rect = self._mouseCommon( x, y, True )

        if region==PAINT_LEFT_ITEMS or region==PAINT_RIGHT_ITEMS:
            if self.ini.getint( "MISC", "mouse_operation" ):
                self.command_ContextMenu()
        elif region==PAINT_LEFT_LOCATION or region==PAINT_RIGHT_LOCATION:
            if self.ini.getint( "MISC", "mouse_operation" ):
                self.command_ContextMenuDir()

    def _onMouseMove( self, x, y, mod ):
        #print "_onMouseMove", x, y
        
        if self.mouse_event_mask : return

        if self.mouse_click_info==None : return
        
        if self.mouse_click_info.mode=="item":
        
            if abs(self.mouse_click_info.x-x)>8 or abs(self.mouse_click_info.y-y)>8:
                if len(self.mouse_click_info.dnd_items)>0:
                    cmailer_native.doDragAndDrop( self.mouse_click_info.dnd_items )
                self.mouse_click_info = None

        elif self.mouse_click_info.mode in ( "log", "log_double_click" ):
            char_x, char_y, region, pane, pane_rect = self._mouseCommon( x, y, False )
            
            log_pane_rect = list( self.logPaneRect() )
            if char_y < log_pane_rect[1]:
                self.command_LogUp()
            elif char_y >= log_pane_rect[3]:
                self.command_LogDown()

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
        char_x, char_y, region, pane, pane_rect = self._mouseCommon( x, y, True )

        if region!=None and region&PAINT_UPPER:
        
            self.mouse_click_info=None
        
            while wheel>0:
                self.command_ScrollUp()
                self.command_ScrollUp()
                self.command_ScrollUp()
                wheel-=1
            while wheel<0:
                self.command_ScrollDown()
                self.command_ScrollDown()
                self.command_ScrollDown()
                wheel+=1

        elif region==PAINT_LOG:
            while wheel>0:
                self.command_LogUp()
                self.command_LogUp()
                self.command_LogUp()
                wheel-=1
            while wheel<0:
                self.command_LogDown()
                self.command_LogDown()
                self.command_LogDown()
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
        return self.left_window_width

    def rightPaneWidth(self):
        return self.width() - self.left_window_width - 1

    def upperPaneHeight(self):
        return self.height() - self.log_window_height - 1

    def lowerPaneHeight(self):
        return self.log_window_height + 1

    def logPaneHeight(self):
        return self.log_window_height

    def fileListItemPaneHeight(self):
        return self.upperPaneHeight() - 3

    def leftPaneRect(self):
        return ( 0, 0, self.left_window_width, self.height() - self.log_window_height - 1 )

    def rightPaneRect(self):
        return ( self.left_window_width+1, 0, self.width(), self.height() - self.log_window_height - 1 )

    def logPaneRect(self):
        return ( 0, self.height()-self.log_window_height-1, self.width(), self.height()-1 )

    def activePaneRect(self):
        if self.focus==MainWindow.FOCUS_LEFT:
            return self.leftPaneRect()
        elif self.focus==MainWindow.FOCUS_RIGHT:
            return self.rightPaneRect()
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
            pane = self.left_pane
            pane_rect = self.leftPaneRect()
        elif self.focus==MainWindow.FOCUS_RIGHT:
            pane = self.right_pane
            pane_rect = self.rightPaneRect()
        else:
            assert(False)

        return ( pane_rect[0], pane_rect[1] + 2 + pane.cursor - pane.scroll_info.pos)

    def leftPane(self):
        return self.left_pane

    def rightPane(self):
        return self.right_pane

    def activePane(self):
        if self.focus==MainWindow.FOCUS_LEFT:
            return self.left_pane
        elif self.focus==MainWindow.FOCUS_RIGHT:
            return self.right_pane
        else:
            assert(False)

    def inactivePane(self):
        if self.focus==MainWindow.FOCUS_LEFT:
            return self.right_pane
        elif self.focus==MainWindow.FOCUS_RIGHT:
            return self.left_pane
        else:
            assert(False)

    ## 左ペインの FileList オブジェクトを取得する
    def leftFileList(self):
        return self.left_pane.file_list

    ## 右ペインの FileList オブジェクトを取得する
    def rightFileList(self):
        return self.right_pane.file_list

    ## アクティブペインの FileList オブジェクトを取得する
    def activeFileList(self):
        if self.focus==MainWindow.FOCUS_LEFT:
            return self.left_pane.file_list
        elif self.focus==MainWindow.FOCUS_RIGHT:
            return self.right_pane.file_list
        else:
            assert(False)

    ## アクティブでないほうのペインの FileList オブジェクトを取得する
    def inactiveFileList(self):
        if self.focus==MainWindow.FOCUS_LEFT:
            return self.right_pane.file_list
        elif self.focus==MainWindow.FOCUS_RIGHT:
            return self.left_pane.file_list
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
        return self._items(self.left_pane)

    ## 右ペインのアイテムのリストを取得する
    def rightItems(self):
        return self._items(self.right_pane)

    ## アクティブペインのアイテムのリストを取得する
    def activeItems(self):
        if self.focus==MainWindow.FOCUS_LEFT:
            return self._items(self.left_pane)
        elif self.focus==MainWindow.FOCUS_RIGHT:
            return self._items(self.right_pane)
        else:
            assert(False)

    ## アクティブではないほうのペインのアイテムのリストを取得する
    def inactiveItems(self):
        if self.focus==MainWindow.FOCUS_LEFT:
            return self._items(self.right_pane)
        elif self.focus==MainWindow.FOCUS_RIGHT:
            return self._items(self.left_pane)
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
        return self._selectedItems(self.left_pane)

    ## 右ペインの選択されているアイテムのリストを取得する
    def rightSelectedItems(self):
        return self._selectedItems(self.right_pane)

    ## アクティブペインの選択されているアイテムのリストを取得する
    def activeSelectedItems(self):
        if self.focus==MainWindow.FOCUS_LEFT:
            return self._selectedItems(self.left_pane)
        elif self.focus==MainWindow.FOCUS_RIGHT:
            return self._selectedItems(self.right_pane)
        else:
            assert(False)

    ## アクティブではないほうのペインの選択されているアイテムのリストを取得する
    def inactiveSelectedItems(self):
        if self.focus==MainWindow.FOCUS_LEFT:
            return self._selectedItems(self.right_pane)
        elif self.focus==MainWindow.FOCUS_RIGHT:
            return self._selectedItems(self.left_pane)
        else:
            assert(False)

    def _cursorItem( self, pane ):
        return pane.file_list.getItem(pane.cursor)

    ## 左ペインのカーソル位置のアイテムを取得する
    def leftCursorItem(self):
        return self._cursorItem(self.left_pane)

    ## 右ペインのカーソル位置のアイテムを取得する
    def rightCursorItem(self):
        return self._cursorItem(self.right_pane)

    ## アクティブペインのカーソル位置のアイテムを取得する
    def activeCursorItem(self):
        if self.focus==MainWindow.FOCUS_LEFT:
            return self._cursorItem(self.left_pane)
        elif self.focus==MainWindow.FOCUS_RIGHT:
            return self._cursorItem(self.right_pane)
        else:
            assert(False)

    ## アクティブではないほうのペインのカーソル位置のアイテムを取得する
    def inactiveCursorItem(self):
        if self.focus==MainWindow.FOCUS_LEFT:
            return self._cursorItem(self.right_pane)
        elif self.focus==MainWindow.FOCUS_RIGHT:
            return self._cursorItem(self.left_pane)
        else:
            assert(False)

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
            pane.cursor = self.cursorFromHistory( pane.file_list, pane.history )
        pane.scroll_info.makeVisible( pane.cursor, self.fileListItemPaneHeight(), 1 )
        if pane==self.left_pane:
            self.paint(PAINT_LEFT)
        else:
            self.paint(PAINT_RIGHT)
        self.appendHistory(pane)
    
    ## 指定したペインのディレクトリを指定したパスにジャンプする
    def jump( self, pane, path ):
        path = ckit.joinPath( pane.file_list.getLocation(), path )
        if os.path.isdir(path):
            dirname = path
            filename = u""
        else:
            dirname, filename = ckit.splitPath(path)
        lister = cmailer_filelist.lister_Default(self,dirname)
        self.jumpLister( pane, lister, filename )

    ## 左ペインのディレクトリを指定したパスにジャンプする
    def leftJump( self, path ):
        self.jump(self.left_pane)

    ## 右ペインのディレクトリを指定したパスにジャンプする
    def rightJump( self, path ):
        self.jump(self.right_pane,path)

    ## アクティブペインのディレクトリを指定したパスにジャンプする
    def activeJump( self, path ):
        if self.focus==MainWindow.FOCUS_LEFT:
            self.jump(self.left_pane,path)
        elif self.focus==MainWindow.FOCUS_RIGHT:
            self.jump(self.right_pane,path)
        else:
            assert(False)

    ## アクティブではないほうのペインのディレクトリを指定したパスにジャンプする
    def inactiveJump( self, path ):
        if self.focus==MainWindow.FOCUS_LEFT:
            self.jump(self.right_pane,path)
        elif self.focus==MainWindow.FOCUS_RIGHT:
            self.jump(self.left_pane,path)
        else:
            assert(False)

    ## 左ペインのディレクトリを指定したリスト機能を使ってジャンプする
    def leftJumpLister( self, lister, name=None, raise_error=False ):
        self.jumpLister( self.left_pane, lister, name, raise_error )

    ## 右ペインのディレクトリを指定したリスト機能を使ってジャンプする
    def rightJumpLister( self, lister, name=None, raise_error=False ):
        self.jumpLister( self.right_pane, lister, name, raise_error )

    ## アクティブペインのディレクトリを指定したリスト機能を使ってジャンプする
    def activeJumpLister( self, lister, name=None, raise_error=False ):
        if self.focus==MainWindow.FOCUS_LEFT:
            self.jumpLister( self.left_pane, lister, name, raise_error )
        elif self.focus==MainWindow.FOCUS_RIGHT:
            self.jumpLister( self.right_pane, lister, name, raise_error )
        else:
            assert(False)

    ## アクティブではないほうのペインのディレクトリを指定したリスト機能を使ってジャンプする
    def inactiveJumpLister( self, lister, name=None, raise_error=False ):
        if self.focus==MainWindow.FOCUS_LEFT:
            self.jumpLister( self.right_pane, lister, name, raise_error )
        elif self.focus==MainWindow.FOCUS_RIGHT:
            self.jumpLister( self.left_pane, lister, name, raise_error )
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
        visible = isinstance( lister, cmailer_filelist.lister_Default )
        pane.history.append( pane.file_list.getLocation(), item.getName(), visible, mark )

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

    def showHiddenFile( self, show ):

        if self.show_hidden == show : return
        self.show_hidden = show

        self.refreshFileList( self.left_pane, True, True )
        self.refreshFileList( self.right_pane, True, True )

        if show:
            self.setStatusMessage( u"隠しファイル : 表示", 3000 )
        else:
            self.setStatusMessage( u"隠しファイル : 非表示", 3000 )

        self.paint(PAINT_LEFT | PAINT_RIGHT)

    def isHiddenFileVisible(self):
        return self.show_hidden

    def setItemFormat( self, itemformat ):
        self.itemformat = itemformat
        self.paint(PAINT_LEFT | PAINT_RIGHT)

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

        self.plane_location_separator = ckit.ThemePlane3x3( self, 'vseparator.png' )
        self.plane_header = ckit.ThemePlane3x3( self, 'header.png' )
        self.plane_footer = ckit.ThemePlane3x3( self, 'footer.png' )
        self.plane_isearch = ckit.ThemePlane3x3( self, 'isearch.png', 1 )
        self.plane_vertical_separator = ckit.ThemePlane3x3( self, 'vseparator.png' )
        self.plane_statusbar = ckit.ThemePlane3x3( self, 'statusbar.png', 1.5 )
        self.plane_commandline = ckit.ThemePlane3x3( self, 'commandline.png', 1 )

        self.plane_isearch.show(False)
        self.plane_commandline.show(False)

        self.theme_enabled = True

        self.updateThemePosSize()
        
    def destroyThemePlane(self):
        self.plane_location_separator.destroy()
        self.plane_header.destroy()
        self.plane_footer.destroy()
        self.plane_isearch.destroy()
        self.plane_vertical_separator.destroy()
        self.plane_statusbar.destroy()
        self.plane_commandline.destroy()
        self.theme_enabled = False

    def updateThemePosSize(self):

        if not self.theme_enabled : return

        client_rect = self.getClientRect()
        offset_x, offset_y = self.charToClient( 0, 0 )
        char_w, char_h = self.getCharSize()

        self.plane_location_separator.setPosSize(    self.left_window_width*char_w+offset_x,   0,                                                           char_w,                char_h+offset_y )
        self.plane_header.setPosSize(                0,                                        1*char_h+offset_y,                                           client_rect[2],        char_h )
        self.plane_footer.setPosSize(                0,                                        (self.height()-self.log_window_height-2)*char_h+offset_y,    client_rect[2],        char_h )
        self.plane_vertical_separator.setPosSize(    self.left_window_width*char_w+offset_x,   2*char_h+offset_y,                                           char_w,                (self.height()-self.log_window_height-4)*char_h )
        self.plane_statusbar.setPosSize(             0,                                        (self.height()-1)*char_h+offset_y,                           client_rect[2],        client_rect[3]-((self.height()-1)*char_h+offset_y) )

    #--------------------------------------------------------------------------

    def updateColor(self):
        self.setBGColor( ckit.getColor("bg"))
        self.setCursorColor( ckit.getColor("cursor0"), ckit.getColor("cursor1") )
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
                option |= [ PAINT_LEFT_LOCATION, PAINT_RIGHT_LOCATION ][self.focus]
            if option & PAINT_FOCUSED_HEADER:
                option |= [ PAINT_LEFT_HEADER, PAINT_RIGHT_HEADER ][self.focus]
            if option & PAINT_FOCUSED_ITEMS:
                option |= [ PAINT_LEFT_ITEMS, PAINT_RIGHT_ITEMS ][self.focus]
            if option & PAINT_FOCUSED_FOOTER:
                option |= [ PAINT_LEFT_FOOTER, PAINT_RIGHT_FOOTER ][self.focus]

        if option & PAINT_LEFT:
            """
            if self.focus==MainWindow.FOCUS_LEFT:
                cursor = self.left_pane.cursor
            else:
                cursor = None
            rect = self.leftPaneRect()

            x = rect[0]
            y = rect[1]
            width = rect[2]-rect[0]
            height = rect[3]-rect[1]

            if option & PAINT_LEFT_LOCATION and height>=1 :
                self._paintFileListLocation( x, y, width, 1, self.left_pane.file_list )
            if option & PAINT_LEFT_HEADER and height>=2 :
                self._paintFileListHeaderInfo( x, y+1, width, 1, self.left_pane.file_list )
            if option & PAINT_LEFT_ITEMS and height>=4 :
                self._paintFileListItems( x, y+2, width, height-3, self.left_pane.file_list, self.left_pane.scroll_info, cursor )
            if option & PAINT_LEFT_FOOTER and height>=1 :
                if self.left_pane.footer_paint_hook:
                    self.left_pane.footer_paint_hook( x, y+height-1, width, 1, self.left_pane.file_list )
                else:
                    self._paintFileListFooterInfo( x, y+height-1, width, 1, self.left_pane.file_list )
            """

        if option & PAINT_RIGHT:
            """
            if self.focus==MainWindow.FOCUS_RIGHT:
                cursor = self.right_pane.cursor
            else:
                cursor = None
            rect = self.rightPaneRect()

            x = rect[0]
            y = rect[1]
            width = rect[2]-rect[0]
            height = rect[3]-rect[1]

            if option & PAINT_RIGHT_LOCATION and height>=1 :
                self._paintFileListLocation( x, y, width, 1, self.right_pane.file_list )
            if option & PAINT_RIGHT_HEADER and height>=2 :
                self._paintFileListHeaderInfo( x, y+1, width, 1, self.right_pane.file_list )
            if option & PAINT_RIGHT_ITEMS and height>=4 :
                self._paintFileListItems( x, y+2, width, height-3, self.right_pane.file_list, self.right_pane.scroll_info, cursor )
            if option & PAINT_RIGHT_FOOTER and height>=1 :
                if self.right_pane.footer_paint_hook:
                    self.right_pane.footer_paint_hook( x, y+height-1, width, 1, self.right_pane.file_list )
                else:
                    self._paintFileListFooterInfo( x, y+height-1, width, 1, self.right_pane.file_list )
            """

        if option & PAINT_VERTICAL_SEPARATOR:
            self._paintVerticalSeparator( self.leftPaneWidth(), 0, 1, self.upperPaneHeight() )

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

    def _paintVerticalSeparator( self, x, y, width, height ):

        attr = ckit.Attribute( fg=ckit.getColor("bar_fg"))

        if height>=1 :
            self.putString( x, y, width, 1, attr, u" " * width )
        if height>=2 :
            self.putString( x, y+1, width, 1, attr, u" " * width )
        if height>=4 :
            for i in xrange(2,height-1):
                self.putString( x, y+i, width, 1, attr, u" " * width )

        if height>=1 :
            self.putString( x, y+height-1, width, 1, attr, u" " * width )

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
        self.keymap[ "Up" ] = self.command_CursorUp
        self.keymap[ "Down" ] = self.command_CursorDown
        self.keymap[ "C-Up" ] = self.command_CursorUpSelectedOrBookmark
        self.keymap[ "C-Down" ] = self.command_CursorDownSelectedOrBookmark
        self.keymap[ "PageUp" ] = self.command_CursorPageUp
        self.keymap[ "PageDown" ] = self.command_CursorPageDown
        self.keymap[ "C-PageUp" ] = self.command_CursorTop
        self.keymap[ "C-PageDown" ] = self.command_CursorBottom
        self.keymap[ "Tab" ] = self.command_FocusOther
        self.keymap[ "C-Tab" ] = self.command_ActivateCmailerNext
        self.keymap[ "Left" ] = self.command_FocusLeftOrGotoParentDir
        self.keymap[ "Right" ] = self.command_FocusRightOrGotoParentDir
        self.keymap[ "Back" ] = self.command_GotoParentDir
        self.keymap[ "A-Left" ] = self.command_MoveSeparatorLeft
        self.keymap[ "A-Right" ] = self.command_MoveSeparatorRight
        self.keymap[ "A-Up" ] = self.command_MoveSeparatorUp
        self.keymap[ "A-Down" ] = self.command_MoveSeparatorDown
        self.keymap[ "C-A-Left" ] = self.command_MoveSeparatorLeftQuick
        self.keymap[ "C-A-Right" ] = self.command_MoveSeparatorRightQuick
        self.keymap[ "C-A-Up" ] = self.command_MoveSeparatorUpQuick
        self.keymap[ "C-A-Down" ] = self.command_MoveSeparatorDownQuick
        self.keymap[ "Return" ] = self.command_Enter
        self.keymap[ "C-Return" ] = self.command_Execute
        self.keymap[ "Escape" ] = self.command_Escape
        self.keymap[ "S-Escape" ] = self.command_CancelTask
        self.keymap[ "End" ] = self.command_DeselectAll
        self.keymap[ "S-End" ] = self.command_Refresh
        self.keymap[ "S-Up" ] = self.command_LogUp
        self.keymap[ "S-Down" ] = self.command_LogDown
        self.keymap[ "S-Left" ] = self.command_LogPageUp
        self.keymap[ "S-Right" ] = self.command_LogPageDown
        self.keymap[ "Minus" ] = self.command_MoveSeparatorCenter
        self.keymap[ "S-Minus" ] = self.command_MoveSeparatorMaximizeH
        self.keymap[ "Space" ] = self.command_SelectDown
        self.keymap[ "S-Space" ] = self.command_SelectUp
        self.keymap[ "C-Space" ] = self.command_SelectRegion
        self.keymap[ "A" ] = self.command_SelectAllFiles
        self.keymap[ "Home" ] = self.command_SelectAllFiles
        self.keymap[ "S-A" ] = self.command_SelectAll
        self.keymap[ "S-Home" ] = self.command_SelectAll
        self.keymap[ "C" ] = self.command_Copy
        self.keymap[ "E" ] = self.command_Edit
        self.keymap[ "S-E" ] = self.command_EditInput
        self.keymap[ "F" ] = self.command_IncrementalSearch
        self.keymap[ "S-F" ] = self.command_Search
        self.keymap[ "S-G" ] = self.command_Grep
        self.keymap[ "I" ] = self.command_Info
        self.keymap[ "H" ] = self.command_JumpHistory
        self.keymap[ "J" ] = self.command_JumpList
        self.keymap[ "S-J" ] = self.command_JumpInput
        self.keymap[ "C-J" ] = self.command_JumpFound
        self.keymap[ "Q" ] = self.command_Quit
        self.keymap[ ckit.KeyEvent( ord('M'), 0, extra=1 ) ] = self.command_Move
        self.keymap[ ckit.KeyEvent( ord('M'), MODKEY_SHIFT, extra=1 ) ] = self.command_MoveInput
        self.keymap[ "O" ] = self.command_ChdirActivePaneToOther
        self.keymap[ "S-O" ] = self.command_ChdirInactivePaneToOther
        self.keymap[ "S" ] = self.command_SetSorter
        self.keymap[ "W" ] = self.command_SelectCompare
        self.keymap[ "S-W" ] = self.command_CompareTools
        self.keymap[ "R" ] = self.command_Rename
        self.keymap[ "S-R" ] = self.command_BatchRename
        self.keymap[ "C-C" ] = self.command_SetClipboard_LogSelectedOrFilename
        self.keymap[ "C-S-C" ] = self.command_SetClipboard_Fullpath
        self.keymap[ "A-C" ] = self.command_SetClipboard_LogAll
        self.keymap[ "B" ] = self.command_BookmarkListLocal
        self.keymap[ "S-B" ] = self.command_BookmarkList
        self.keymap[ "C-B" ] = self.command_Bookmark
        self.keymap[ "X" ] = self.command_CommandLine
        self.keymap[ "Z" ] = self.command_ConfigMenu
        self.keymap[ "S-Z" ] = self.command_ConfigMenu2
        self.keymap[ "S-Colon" ] = self.command_SetFilter
        self.keymap[ "Colon" ] = self.command_SetFilterList
        self.keymap[ "BackSlash" ] = self.command_GotoRootDir
        if default_keymap in ("101","106"):
            self.keymap[ "D" ] = self.command_SelectDrive
            self.keymap[ "K" ] = self.command_Delete
            self.keymap[ "S-K" ] = self.command_Delete2
            self.keymap[ "L" ] = self.command_View
            self.keymap[ ckit.KeyEvent( ord('M'), 0, extra=0 ) ] = self.command_Mkdir
        elif default_keymap in ("101afx","106afx"):
            self.keymap[ "D" ] = self.command_Delete
            self.keymap[ "S-D" ] = self.command_Delete2
            self.keymap[ "K" ] = self.command_Mkdir
            self.keymap[ "L" ] = self.command_SelectDrive
            self.keymap[ "V" ] = self.command_View
        if default_keymap in ("101","101afx"):
            self.keymap[ "Slash" ] = self.command_ContextMenu
            self.keymap[ "S-Slash" ] = self.command_ContextMenuDir
            self.keymap[ "Quote" ] = self.command_SelectUsingFilterList
            self.keymap[ "S-Quote" ] = self.command_SelectUsingFilter
        elif default_keymap in ("106","106afx"):
            self.keymap[ "BackSlash" ] = self.command_ContextMenu
            self.keymap[ "S-BackSlash" ] = self.command_ContextMenuDir
            self.keymap[ "Atmark" ] = self.command_SelectUsingFilterList
            self.keymap[ "S-Atmark" ] = self.command_SelectUsingFilter

        self.jump_list = [
        ]

        self.filter_list = [
        ]

        self.select_filter_list = [
        ]

        self.compare_list = [
            #( u"F : 気にしない",                    cmailer_filelist.compare_Default() ),
            #( u"S : サイズが同じ",                  cmailer_filelist.compare_Default(cmp_size=0) ),
            #( u"T : タイムスタンプが同じ",          cmailer_filelist.compare_Default(cmp_timestamp=0) ),
            #( u"A : サイズ/タイムスタンプが同じ",   cmailer_filelist.compare_Default(cmp_size=0,cmp_timestamp=0) ),
            #( u"M : 選択されている",                cmailer_filelist.compare_Selected() ),
        ]
        
        self.compare_tool_list = [
            ( u"ファイル比較",      self.command_Diff ),
            ( u"ディレクトリ比較",  self.command_DirCompare ),
        ]

        self.sorter_list = [
            #( u"F : ファイル名",     cmailer_filelist.sorter_ByName(),       cmailer_filelist.sorter_ByName( order=-1 ) ),
            #( u"E : 拡張子",         cmailer_filelist.sorter_ByExt(),        cmailer_filelist.sorter_ByExt( order=-1 ) ),
            #( u"S : サイズ",         cmailer_filelist.sorter_BySize(),       cmailer_filelist.sorter_BySize( order=-1 ) ),
            #( u"T : タイムスタンプ", cmailer_filelist.sorter_ByTimeStamp(),  cmailer_filelist.sorter_ByTimeStamp( order=-1 ) ),
        ]

        self.association_list = [
        ]
        
        self.itemformat_list = [
            #( u"1 : 全て表示 : filename  .ext  99.9K YY/MM/DD HH:MM:SS",     cmailer_filelist.itemformat_Name_Ext_Size_YYMMDD_HHMMSS ),
            #( u"2 : 秒を省略 : filename  .ext  99.9K YY/MM/DD HH:MM",        cmailer_filelist.itemformat_Name_Ext_Size_YYMMDD_HHMM ),
            #( u"0 : 名前のみ : filename.ext",                                cmailer_filelist.itemformat_NameExt ),
        ]
        
        #self.itemformat = cmailer_filelist.itemformat_Name_Ext_Size_YYMMDD_HHMMSS

        self.commandline_list = [
            self.launcher,
            cmailer_commandline.commandline_Int32Hex(),
            cmailer_commandline.commandline_Calculator(),
        ]

        self.launcher.command_list = [
            ( u"Reload",           self.command_Reload ),
            ( u"About",            self.command_About ),
            ( u"Wallpaper",        self.command_Wallpaper ),
            ( u"ReceiveTest",      self.command_ReceiveTest ),
            ( u"_MemoryStat",      self.command_MemoryStat ),
            ( u"_RefererTree",     self.command_RefererTree ),
        ]
        
        cmailer_usernamespace.reload( self.config_filename )
        cmailer_usernamespace.call("configure",self)

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
            self.ini.add_section("RIGHTPANE")
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
            self.ini.add_section("BATCHRENAME")
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
            self.ini.add_section("SPLIT")
        except ConfigParser.DuplicateSectionError:
            pass

        try:
            self.ini.add_section("UPDATE")
        except ConfigParser.DuplicateSectionError:
            pass

        try:
            self.ini.add_section("DRIVES")
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
        if not self.ini.has_option( "GEOMETRY", "left_window_width" ):
            self.ini.set( "GEOMETRY", "left_window_width", str( (self.ini.getint( "GEOMETRY", "width" )-1)/2 ) )

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

        if not self.ini.has_option( "BATCHRENAME", "old" ):
            self.ini.set( "BATCHRENAME", "old", "" )
        if not self.ini.has_option( "BATCHRENAME", "new" ):
            self.ini.set( "BATCHRENAME", "new", "" )
        if not self.ini.has_option( "BATCHRENAME", "regexp" ):
            self.ini.set( "BATCHRENAME", "regexp", str(0) )
        if not self.ini.has_option( "BATCHRENAME", "ignorecase" ):
            self.ini.set( "BATCHRENAME", "ignorecase", str(1) )

        if not self.ini.has_option( "SPLIT", "size" ):
            self.ini.set( "SPLIT", "size", "100M" )

        if not self.ini.has_option( "UPDATE", "check_frequency" ):
            self.ini.set( "UPDATE", "check_frequency", "1000000" )
        if not self.ini.has_option( "UPDATE", "last_checked_date" ):
            self.ini.set( "UPDATE", "last_checked_date", "0" )

        if not self.ini.has_option( "ACCOUNT", "username" ):
            self.ini.set( "ACCOUNT", "username", "" )
        if not self.ini.has_option( "ACCOUNT", "password" ):
            self.ini.set( "ACCOUNT", "password", "" )

        if not self.ini.has_option( "MISC", "default_keymap" ):
            self.ini.set( "MISC", "default_keymap", "106" )
        if not self.ini.has_option( "MISC", "esc_action" ):
            self.ini.set( "MISC", "esc_action", "none" )
        if not self.ini.has_option( "MISC", "mouse_operation" ):
            self.ini.set( "MISC", "mouse_operation", "1" )
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
            self.ini.set( "GEOMETRY", "left_window_width", str(self.left_window_width) )

            #self.left_pane.history.save( self.ini, "LEFTPANE" )
            #self.right_pane.history.save( self.ini, "RIGHTPANE" )

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

    def startup( self, left_location=None, right_location=None ):

        print cmailer_resource.startupString()

        """
        # 左ペインの初期位置
        if left_location:
            location = left_location
        else:
            last_history = self.left_pane.history.findLastVisible()
            if last_history:
                location = last_history[0]
            else:
                location = os.getcwdu()
        try:
            self.jumpLister( self.left_pane, cmailer_filelist.lister_Default(self,location), raise_error=True )
        except:
            self.jumpLister( self.left_pane, cmailer_filelist.lister_Default(self,os.getcwd()) )

        # 右ペインの初期位置
        if right_location:
            location = right_location
        else:
            last_history = self.right_pane.history.findLastVisible()
            if last_history:
                location = last_history[0]
            else:
                location = os.getcwdu()
        try:
            self.jumpLister( self.right_pane, cmailer_filelist.lister_Default(self,location), raise_error=True )
        except:
            self.jumpLister( self.right_pane, cmailer_filelist.lister_Default(self,os.getcwd()) )
        """

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
    def command_CursorUp(self):
        pane = self.activePane()
        pane.cursor -= 1
        if pane.cursor<0 : pane.cursor=0
        pane.scroll_info.makeVisible( pane.cursor, self.fileListItemPaneHeight(), 1 )
        self.paint(PAINT_FOCUSED_ITEMS)

    ## カーソルを1つ下に移動させる
    def command_CursorDown(self):
        pane = self.activePane()
        pane.cursor += 1
        if pane.cursor>pane.file_list.numItems()-1 : pane.cursor=pane.file_list.numItems()-1
        pane.scroll_info.makeVisible( pane.cursor, self.fileListItemPaneHeight(), 1 )
        self.paint(PAINT_FOCUSED_ITEMS)

    ## 上方向の選択されているアイテムまでカーソルを移動させる
    def command_CursorUpSelected(self):
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
    def command_CursorDownSelected(self):
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
    def command_CursorUpBookmark(self):
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
    def command_CursorDownBookmark(self):
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
    def command_CursorUpSelectedOrBookmark(self):
        pane = self.activePane()
        if pane.file_list.selected():
            self.command_CursorUpSelected()
        else:
            self.command_CursorUpBookmark()

    ## 下方向の選択またはブックマークされているアイテムまでカーソルを移動させる
    def command_CursorDownSelectedOrBookmark(self):
        pane = self.activePane()
        if pane.file_list.selected():
            self.command_CursorDownSelected()
        else:
            self.command_CursorDownBookmark()

    ## 1ページ上方向にカーソルを移動させる
    def command_CursorPageUp(self):
        pane = self.activePane()
        if pane.cursor>pane.scroll_info.pos + 1 :
            pane.cursor = pane.scroll_info.pos + 1
        else:
            pane.cursor -= self.fileListItemPaneHeight()
            if pane.cursor<0 : pane.cursor=0
            pane.scroll_info.makeVisible( pane.cursor, self.fileListItemPaneHeight(), 1 )
        self.paint(PAINT_FOCUSED_ITEMS)

    ## 1ページ下方向にカーソルを移動させる
    def command_CursorPageDown(self):
        pane = self.activePane()
        if pane.cursor<pane.scroll_info.pos+self.fileListItemPaneHeight()-2:
            pane.cursor = pane.scroll_info.pos+self.fileListItemPaneHeight()-2
        else:
            pane.cursor += self.fileListItemPaneHeight()
        if pane.cursor>pane.file_list.numItems()-1 : pane.cursor=pane.file_list.numItems()-1
        pane.scroll_info.makeVisible( pane.cursor, self.fileListItemPaneHeight(), 1 )
        self.paint(PAINT_FOCUSED_ITEMS)

    ## リストの先頭にカーソルを移動させる
    def command_CursorTop(self):
        pane = self.activePane()
        pane.cursor=0
        pane.scroll_info.makeVisible( pane.cursor, self.fileListItemPaneHeight(), 1 )
        self.paint(PAINT_FOCUSED_ITEMS)

    ## リストの末尾にカーソルを移動させる
    def command_CursorBottom(self):
        pane = self.activePane()
        pane.cursor=pane.file_list.numItems()-1
        pane.scroll_info.makeVisible( pane.cursor, self.fileListItemPaneHeight(), 1 )
        self.paint(PAINT_FOCUSED_ITEMS)

    ## 一行上方向にスクロールする
    def command_ScrollUp(self):
        pane = self.activePane()
        if pane.scroll_info.pos-1 >= 0:
            pane.scroll_info.pos -= 1
            pane.cursor -= 1
        self.paint(PAINT_FOCUSED_ITEMS)

    ## 一行下方向にスクロールする
    def command_ScrollDown(self):
        pane = self.activePane()
        if pane.scroll_info.pos+1 < pane.file_list.numItems()-self.fileListItemPaneHeight()+2:
            pane.cursor += 1
            pane.scroll_info.pos += 1
        self.paint(PAINT_FOCUSED_ITEMS)

    ## アクティブではないほうのペインにフォーカスする
    def command_FocusOther(self):
        if self.focus==MainWindow.FOCUS_LEFT:
            self.focus = MainWindow.FOCUS_RIGHT
        elif self.focus==MainWindow.FOCUS_RIGHT:
            self.focus = MainWindow.FOCUS_LEFT
        self.paint( PAINT_LEFT | PAINT_RIGHT )

    ## 親ディレクトリに移動する
    def command_GotoParentDir(self):
        pane = self.activePane()
        name = pane.file_list.getItem(pane.cursor).name
        try:
            new_lister, select_name = pane.file_list.getLister().getParent()
        except:
            return
        self.jumpLister( pane, new_lister, select_name )

    ## ルートディレクトリに移動する
    def command_GotoRootDir(self):
        pane = self.activePane()
        new_lister = pane.file_list.getLister().getRoot()
        self.jumpLister( pane, new_lister )

    ## 左ペインにフォーカスする
    def command_FocusLeft(self):
        if self.focus==MainWindow.FOCUS_RIGHT:
            self.focus = MainWindow.FOCUS_LEFT
        self.paint( PAINT_LEFT | PAINT_RIGHT )

    ## 右ペインにフォーカスする
    def command_FocusRight(self):
        if self.focus==MainWindow.FOCUS_LEFT:
            self.focus = MainWindow.FOCUS_RIGHT
        self.paint( PAINT_LEFT | PAINT_RIGHT )

    ## 左ペインにフォーカスされていれば親ディレクトリに移動し、そうでなければ左ペインにフォーカスする
    def command_FocusLeftOrGotoParentDir(self):
        if self.focus==MainWindow.FOCUS_LEFT:
            return self.command_GotoParentDir()
        self.command_FocusLeft()

    ## 右ペインにフォーカスされていれば親ディレクトリに移動し、そうでなければ右ペインにフォーカスする
    def command_FocusRightOrGotoParentDir(self):
        if self.focus==MainWindow.FOCUS_RIGHT:
            return self.command_GotoParentDir()
        self.command_FocusRight()

    ## カーソル位置のアイテムの選択状態を切り替える
    def command_Select(self):
        pane = self.activePane()
        pane.file_list.selectItem(pane.cursor)
        self.paint( PAINT_FOCUSED_ITEMS | PAINT_FOCUSED_HEADER )

    ## カーソル位置のアイテムの選択状態を切り替えて、カーソルを1つ下に移動する
    def command_SelectDown(self):
        self.command_Select()
        self.command_CursorDown()
        self.paint( PAINT_FOCUSED_ITEMS | PAINT_FOCUSED_HEADER )

    ## カーソル位置のアイテムの選択状態を切り替えて、カーソルを1つ上に移動する
    def command_SelectUp(self):
        self.command_Select()
        self.command_CursorUp()
        self.paint( PAINT_FOCUSED_ITEMS | PAINT_FOCUSED_HEADER )

    ## 上方向の最も近い選択アイテムからカーソル位置までの全てのアイテムを選択する
    def command_SelectRegion(self):
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
    def command_SelectAll(self):
        pane = self.activePane()
        for i in xrange(pane.file_list.numItems()):
            pane.file_list.selectItem(i)
        self.paint( PAINT_FOCUSED_ITEMS | PAINT_FOCUSED_HEADER )

    ## ファイルリスト中の全てのファイルアイテムの選択状態を切り替える
    def command_SelectAllFiles(self):
        pane = self.activePane()
        for i in xrange(pane.file_list.numItems()):
            item = pane.file_list.getItem(i)
            if not item.isdir():
                pane.file_list.selectItem(i)
        self.paint( PAINT_FOCUSED_ITEMS | PAINT_FOCUSED_HEADER )

    ## ファイルリスト中の全てのアイテムの選択を解除する
    def command_DeselectAll(self):
        pane = self.activePane()
        for i in xrange(pane.file_list.numItems()):
            pane.file_list.selectItem( i, False )
        self.paint( PAINT_FOCUSED_ITEMS | PAINT_FOCUSED_HEADER )

    ## 左右のペインを分離するセパレータを左方向に動かす
    def command_MoveSeparatorLeft(self):
        self.left_window_width -= 3
        if self.left_window_width<0 : self.left_window_width=0
        self.updateThemePosSize()
        self.paint( PAINT_UPPER )

    ## 左右のペインを分離するセパレータを右方向に動かす
    def command_MoveSeparatorRight(self):
        self.left_window_width += 3
        if self.left_window_width>self.width()-1 : self.left_window_width=self.width()-1
        self.updateThemePosSize()
        self.paint( PAINT_UPPER )

    ## 上下のペインを分離するセパレータを上方向に動かす
    def command_MoveSeparatorUp(self):

        log_window_height_old = self.log_window_height
        self.log_window_height += 3
        if self.log_window_height>self.height()-4 : self.log_window_height=self.height()-4
        
        self.log_pane.scroll_info.pos -= self.log_window_height-log_window_height_old
        if self.log_pane.scroll_info.pos>self.log_pane.log.numLines()-self.logPaneHeight() : self.log_pane.scroll_info.pos=self.log_pane.log.numLines()-self.logPaneHeight()
        if self.log_pane.scroll_info.pos<0 : self.log_pane.scroll_info.pos=0

        self.updateThemePosSize()
        self.paint()

    ## 上下のペインを分離するセパレータを下方向に動かす
    def command_MoveSeparatorDown(self):

        log_window_height_old = self.log_window_height
        self.log_window_height -= 3
        if self.log_window_height<0 : self.log_window_height=0

        self.log_pane.scroll_info.pos -= self.log_window_height-log_window_height_old
        if self.log_pane.scroll_info.pos>self.log_pane.log.numLines()-self.logPaneHeight() : self.log_pane.scroll_info.pos=self.log_pane.log.numLines()-self.logPaneHeight()
        if self.log_pane.scroll_info.pos<0 : self.log_pane.scroll_info.pos=0

        self.updateThemePosSize()
        self.paint()

    ## 左右のペインを分離するセパレータを左方向に高速に動かす
    #
    #  中央か端に達するまで、セパレータを左方向に動かします。
    #
    def command_MoveSeparatorLeftQuick(self):
        center = (self.width()-1) / 2
        if self.left_window_width > center :
            self.left_window_width = center
        else:
            self.left_window_width = 0
        self.updateThemePosSize()
        self.paint( PAINT_UPPER )

    ## 左右のペインを分離するセパレータを右方向に高速に動かす
    #
    #  中央か端に達するまで、セパレータを右方向に動かします。
    #
    def command_MoveSeparatorRightQuick(self):
        center = (self.width()-1) / 2
        if self.left_window_width < center :
            self.left_window_width = center
        else:
            self.left_window_width = self.width()-1
        self.updateThemePosSize()
        self.paint( PAINT_UPPER )

    ## 上下のペインを分離するセパレータを上方向に高速に動かす
    #
    #  縦3分割した位置に達するまで、セパレータを上方向に動かします。
    #
    def command_MoveSeparatorUpQuick(self):
        
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

        self.updateThemePosSize()
        self.paint()

    ## 上下のペインを分離するセパレータを下方向に高速に動かす
    #
    #  縦3分割した位置に達するまで、セパレータを下方向に動かします。
    #
    def command_MoveSeparatorDownQuick(self):

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

        self.updateThemePosSize()
        self.paint()

    ## 左右のペインを分離するセパレータを中央にリセットする
    def command_MoveSeparatorCenter(self):
        self.left_window_width = (self.width()-1) / 2
        self.updateThemePosSize()
        self.paint()

    ## 左右のペインを分離するセパレータを、アクティブなペインが最大化するように、片方に寄せる
    def command_MoveSeparatorMaximizeH(self):
        if self.focus==MainWindow.FOCUS_LEFT:
            self.left_window_width=self.width()-1
        elif self.focus==MainWindow.FOCUS_RIGHT:
            self.left_window_width=0
        self.updateThemePosSize()
        self.paint( PAINT_UPPER )

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
    def command_Enter(self):

        if self.enter_hook:
            if self.enter_hook():
                return True

        pane = self.activePane()
        location = pane.file_list.getLocation()
        item = pane.file_list.getItem(pane.cursor)

        if hasattr(item,"getLink"):
            link_entity = item.getLink()
            if link_entity:
                item = link_entity

        if item.isdir():
            new_lister = pane.file_list.getLister().getChild(item.getName())
            self.jumpLister( pane, new_lister )

        else:
            ext = os.path.splitext(item.name)[1].lower()

            for association in self.association_list:
                for pattern in association[0].split():
                    if fnmatch.fnmatch( item.name, pattern ):
                        association[1](item)
                        return

            else:
                self._viewCommon( location, item )


    ## カーソル位置のアイテムに対して、OSで関連付けられた処理を実行する
    def command_Execute(self):
        pane = self.activePane()
        item = pane.file_list.getItem(pane.cursor)
        fullpath = os.path.join( pane.file_list.getLocation(), item.name )
        self.appendHistory( pane, True )
        self.subThreadCall( ckit.shellExecute, ( None, None, fullpath.replace('/','\\'), u"", pane.file_list.getLocation().replace('/','\\') ) )

    ## ESCキー相当の処理を実行する
    #
    #  ESCキーの動作は、設定メニュー2で変更することが出来ます。
    #
    def command_Escape(self):
        esc_action = self.ini.get( "MISC", "esc_action" )
        if esc_action == "inactivate":
            self.inactivate()

    ## バックグラウンドタスクを全てキャンセルする
    def command_CancelTask(self):
        for task_queue in self.task_queue_stack:
            task_queue.cancel()

    ## アクティブペインのファイルリストを再読み込みする
    def command_Refresh(self):
        self.refreshFileList( self.activePane(), True, False )
        self.paint(PAINT_FOCUSED)

    ## ログペインを1行上方向にスクロールする
    def command_LogUp(self):
        self.log_pane.scroll_info.pos -= 1
        if self.log_pane.scroll_info.pos<0 : self.log_pane.scroll_info.pos=0
        self.paint( PAINT_LOG )

    ## ログペインを1行下方向にスクロールする
    def command_LogDown(self):
        self.log_pane.scroll_info.pos += 1
        if self.log_pane.scroll_info.pos>self.log_pane.log.numLines()-self.logPaneHeight() : self.log_pane.scroll_info.pos=self.log_pane.log.numLines()-self.logPaneHeight()
        if self.log_pane.scroll_info.pos<0 : self.log_pane.scroll_info.pos=0
        self.paint( PAINT_LOG )

    ## ログペインを1ページ上方向にスクロールする
    def command_LogPageUp(self):
        self.log_pane.scroll_info.pos -= self.logPaneHeight()
        if self.log_pane.scroll_info.pos<0 : self.log_pane.scroll_info.pos=0
        self.paint( PAINT_LOG )

    ## ログペインを1ページ下方向にスクロールする
    def command_LogPageDown(self):
        self.log_pane.scroll_info.pos += self.logPaneHeight()
        if self.log_pane.scroll_info.pos>self.log_pane.log.numLines()-self.logPaneHeight() : self.log_pane.scroll_info.pos=self.log_pane.log.numLines()-self.logPaneHeight()
        if self.log_pane.scroll_info.pos<0 : self.log_pane.scroll_info.pos=0
        self.paint( PAINT_LOG )

    def _deleteCommon( self, use_builtin_delete ):

        pane = self.activePane()
        item_filter = pane.file_list.getFilter()

        items = []
        
        if not use_builtin_delete:
            for i in xrange(pane.file_list.numItems()):
                item = pane.file_list.getItem(i)
                if item.selected() and hasattr(item,"getFullpath"):
                    items.append(item)
            if not len(items):
                use_builtin_delete = True
        
        if use_builtin_delete:
            for i in xrange(pane.file_list.numItems()):
                item = pane.file_list.getItem(i)
                if item.selected() and hasattr(item,"delete"):
                    items.append(item)

        if len(items):

            if use_builtin_delete:
                result = cmailer_msgbox.popMessageBox( self, MessageBox.TYPE_YESNO, u"削除の確認", u"削除しますか？" )
                if result!=MessageBox.RESULT_YES : return
            else:
                result = cmailer_msgbox.popMessageBox( self, MessageBox.TYPE_YESNO, u"ごみ箱への投棄の確認", u"ごみ箱へ投棄しますか？" )
                if result!=MessageBox.RESULT_YES : return

            def deselectItem(item):
                for i in xrange(pane.file_list.numItems()):
                    if pane.file_list.getItem(i) is item:
                        pane.file_list.selectItem(i,False)
                        if pane == self.left_pane:
                            region = PAINT_LEFT
                        else:
                            region = PAINT_RIGHT
                        self.paint(region)
                        return

            def jobDelete( job_item ):
                
                # ビジーインジケータ On
                self.setProgressValue(None)
                    
                if use_builtin_delete:
                    for item in items:
                    
                        def schedule():
                            if job_item.isCanceled():
                                return True
                            if job_item.waitPaused():
                                self.setProgressValue(None)
                    
                        if schedule(): break
                    
                        item.delete( True, item_filter, schedule, sys.stdout.write )
                        if not job_item.isCanceled():
                            deselectItem(item)
                else:
                    filename_list = []
                    print u'ごみ箱に投棄 :'
                    for item in items:
                        filename = item.getFullpath()
                        if item.isdir():
                            print u'  ディレクトリ : %s' % filename
                        else:
                            print u'  ファイル : %s' % filename
                        filename_list.append(filename)
                    ckit.deleteFilesUsingRecycleBin( self.getHWND(), filename_list )

            def jobDeleteFinished( job_item ):

                # ビジーインジケータ Off
                self.clearProgress()

                if job_item.isCanceled():
                    print u'中断しました.\n'
                else:
                    print "Done.\n"
                    
                self.refreshFileList( self.left_pane, True, True )
                self.refreshFileList( self.right_pane, True, True )
                self.paint( PAINT_LEFT | PAINT_RIGHT )

            self.appendHistory( pane, True )

            job_item = ckit.JobItem( jobDelete, jobDeleteFinished )
            self.taskEnqueue( job_item, u"削除" )

    ## 選択されているアイテムを削除する(デフォルトの方法で)
    #
    #  CraftMailerでは、メーラに内蔵された削除機能と、OSのゴミ箱を使った削除を選択することができます。
    #  command_Delete ではデフォルトに設定された方法で削除を実行します。
    #  削除のデフォルト動作は、設定メニュー2で変更することが出来ます。
    #
    def command_Delete(self):
        delete_behavior = self.ini.get( "MISC", "delete_behavior" )
        if delete_behavior=="recycle_bin":
            use_builtin_delete = False
        elif delete_behavior=="builtin":
            use_builtin_delete = True
        self._deleteCommon(use_builtin_delete)

    ## 選択されているアイテムを削除する(デフォルトではない方法で)
    #
    #  CraftMailerでは、メーラに内蔵された削除機能と、OSのゴミ箱を使った削除を選択することができます。
    #  command_Delete2 ではデフォルトではない方法で削除を実行します。
    #  削除のデフォルト動作は、設定メニュー2で変更することが出来ます。
    #
    def command_Delete2(self):
        delete_behavior = self.ini.get( "MISC", "delete_behavior" )
        if delete_behavior=="recycle_bin":
            use_builtin_delete = False
        elif delete_behavior=="builtin":
            use_builtin_delete = True
        use_builtin_delete = not use_builtin_delete
        self._deleteCommon(use_builtin_delete)

    ## 選択されているアイテムを、もう片方のペインに対してコピーする
    def command_Copy(self):
        active_pane = self.activePane()
        inactive_pane = self.inactivePane()

        if not hasattr(inactive_pane.file_list.getLister(),"getCopyDst"):
            return

        items = []
        for i in xrange(active_pane.file_list.numItems()):
            item = active_pane.file_list.getItem(i)
            if item.selected():
                items.append(item)

        if len(items)<=0 : return

        if self.ini.getint("MISC","confirm_copy"):
            result = cmailer_msgbox.popMessageBox( self, MessageBox.TYPE_YESNO, u"コピーの確認", u"コピーしますか？" )
            if result!=MessageBox.RESULT_YES : return

        self._copyMoveCommon( active_pane, active_pane.file_list.getLister(), inactive_pane.file_list.getLister(), items, "c", active_pane.file_list.getFilter() )

    ## 選択されているアイテムを、もう片方のペインに対して移動する
    def command_Move(self):

        active_pane = self.activePane()
        inactive_pane = self.inactivePane()

        if not hasattr(inactive_pane.file_list.getLister(),"getCopyDst"):
            return

        items = []
        for i in xrange(active_pane.file_list.numItems()):
            item = active_pane.file_list.getItem(i)
            if item.selected() and hasattr(item,"delete"):
                items.append(item)

        if len(items)<=0 : return

        if self.ini.getint("MISC","confirm_move"):
            result = cmailer_msgbox.popMessageBox( self, MessageBox.TYPE_YESNO, u"移動の確認", u"移動しますか？" )
            if result!=MessageBox.RESULT_YES : return

        self._copyMoveCommon( active_pane, active_pane.file_list.getLister(), inactive_pane.file_list.getLister(), items, "m", active_pane.file_list.getFilter() )

    ## 選択されているアイテムを、入力したディレクトリパスに移動する
    def command_MoveInput(self):
        pane = self.activePane()
        items = []
        for i in xrange(pane.file_list.numItems()):
            item = pane.file_list.getItem(i)
            if item.selected() and hasattr(item,"delete"):
                items.append(item)

        if len(items)<=0 : return


        def statusString_IsDir( update_info ):
            move_dst_location = ckit.joinPath( pane.file_list.getLocation(), update_info.text )
            if update_info.text and os.path.isdir(move_dst_location):
                return u"OK"
            else:
                return u"  "

        result = self.commandLine( u"MoveTo", auto_complete=False, autofix_list=["\\/","."], candidate_handler=cmailer_misc.candidate_Filename(pane.file_list.getLocation()), status_handler=statusString_IsDir )
        if result==None : return

        move_dst_location = ckit.joinPath( pane.file_list.getLocation(), result )

        child_lister = pane.file_list.getLister().getChild(result)
        self._copyMoveCommon( pane, pane.file_list.getLister(), child_lister, items, "m", pane.file_list.getFilter() )
        child_lister.destroy()

    ## 選択されているアイテムをエディタで編集する
    #
    #  editor が呼び出し可能オブジェクトであれば、それを呼び出します。
    #  その際、引数には ( ファイルアイテムオブジェクト, (行番号,カラム), カレントディレクトリ ) が渡ります。
    #  editor が呼び出し可能オブジェクトでなければ、テキストエディタのプログラムファイル名とみなし、shellExecute を使ってエディタを起動します。
    #
    def command_Edit(self):
        
        pane = self.activePane()
        items = []
        
        def appendItem(item):
            if hasattr(item,"getLink"):
                link_entity = item.getLink()
                if link_entity:
                    item = link_entity
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
            for item in items:
                if item.isdir() : continue
                if not hasattr(item,"getFullpath") : continue
                if callable(self.editor):
                    self.editor( item, (1,1), pane.file_list.getLocation() )
                else:
                    ckit.shellExecute( None, None, self.editor, '"%s"'% os.path.normpath(item.getFullpath()), pane.file_list.getLocation() )

        self.appendHistory( pane, True )

        self.subThreadCall( editItems, () )

    ## 入力したファイル名でファイルを編集する
    #
    #  入力されたファイルが既存のファイルであれば、そのファイルを編集します。
    #  入力されたファイルが存在しないファイル名であれば、新規のテキストファイルを作成し、それを編集します。
    #
    def command_EditInput(self):
        pane = self.activePane()

        if not hasattr(pane.file_list.getLister(),"touch"):
            return

        result = self.commandLine( u"Edit", auto_complete=False, autofix_list=["\\/","."], candidate_handler=cmailer_misc.candidate_Filename(pane.file_list.getLocation()) )
        if result==None : return

        try:
            item = pane.file_list.getLister().touch(result)
        except Exception, e:
            print u'ERROR : 編集失敗'
            print "  %s" % unicode(str(e),'mbcs')
            cmailer_debug.printErrorInfo()
            return
        
        if item.isdir():
            return

        def editItem():
            if callable(self.editor):
                self.editor( item, (1,1), pane.file_list.getLocation() )
            else:
                ckit.shellExecute( None, None, self.editor, '"%s"'%item.getFullpath(), pane.file_list.getLocation() )

        self.appendHistory( pane, True )

        self.subThreadCall( editItem, () )

        self.paint(PAINT_FOCUSED)

    ## ジャンプリストを表示しジャンプする
    #
    #  jump_list に登録されたジャンプ先をリスト表示します。\n
    #  jump_list は、( 表示名, ジャンプ先のパス ) という形式のタプルが登録されているリストです。
    #
    def command_JumpList(self):

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

        self.jumpLister( pane, cmailer_filelist.lister_Default(self,newdirname) )

    ## 履歴リストを表示しジャンプする
    def command_JumpHistory(self):

        left_pane = self.left_pane
        right_pane = self.right_pane

        pane = self.activePane()

        def onKeyDown( vk, mod ):

            if vk==VK_LEFT and mod==0:
                if pane==right_pane:
                    list_window.switch_left = True
                    list_window.quit()
                return True

            elif vk==VK_RIGHT and mod==0:
                if pane==left_pane:
                    list_window.switch_right = True
                    list_window.quit()
                return True

            elif vk==VK_DELETE and mod==0:
                select = list_window.getResult()
                pane.history.remove( items[select][0] )
                del items[select]
                list_window.remove(select)
                return True

        list_window = None

        while True:

            if pane==left_pane:
                title = u"履歴(左)"
            elif pane==right_pane:
                title = u"履歴(右)"
            else:
                assert(0)

            # ちらつきを防止するために ListWindow の破棄を遅延する
            list_window_old = list_window

            items = filter( lambda item : item[2], pane.history.items )
            list_items = map( lambda item : cmailer_listwindow.ListItem( item[0], item[3] ), items )
            
            def onStatusMessage( width, select ):
                return u""

            pos = self.centerOfWindowInPixel()
            list_window = cmailer_listwindow.ListWindow( pos[0], pos[1], 5, 1, self.width()-5, self.height()-3, self, self.ini, title, list_items, initial_select=0, onekey_search=False, keydown_hook=onKeyDown, statusbar_handler=onStatusMessage )
            list_window.switch_left = False
            list_window.switch_right = False

            if list_window_old:
                list_window_old.destroy()

            self.enable(False)
            list_window.messageLoop()
            result = list_window.getResult()
            self.enable(True)

            if list_window.switch_left:
                pane = left_pane
            elif list_window.switch_right:
                pane = right_pane
            else:
                break

        self.activate()
        list_window.destroy()

        if result<0 : return

        newdirname = items[result][0]

        pane = self.activePane()

        self.jumpLister( pane, cmailer_filelist.lister_Default(self,newdirname) )

    ## パスを入力しジャンプする
    def command_JumpInput(self):
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

        self.jumpLister( pane, cmailer_filelist.lister_Default(self,dirname), filename )

    ## SearchやGrepの検索結果リストを表示しジャンプする
    def command_JumpFound(self):

        left_pane = self.left_pane
        right_pane = self.right_pane

        pane = self.activePane()

        def onKeyDown( vk, mod ):

            if vk==VK_LEFT and mod==0:
                if pane==right_pane:
                    list_window.switch_left = True
                    list_window.quit()
                return True

            elif vk==VK_RIGHT and mod==0:
                if pane==left_pane:
                    list_window.switch_right = True
                    list_window.quit()
                return True

        list_window = None

        while True:

            if pane==left_pane:
                title = u"検索結果(左)"
            elif pane==right_pane:
                title = u"検索結果(右)"
            else:
                assert(0)

            # ちらつきを防止するために ListWindow の破棄を遅延する
            list_window_old = list_window

            list_items = map( lambda item : ckit.normPath(item.getFullpath()), pane.found_items )
            
            def onStatusMessage( width, select ):
                return u""

            pos = self.centerOfWindowInPixel()
            list_window = cmailer_listwindow.ListWindow( pos[0], pos[1], 16, 1, self.width()-5, self.height()-3, self, self.ini, title, list_items, initial_select=0, onekey_search=False, return_modkey=True, keydown_hook=onKeyDown, statusbar_handler=onStatusMessage )
            list_window.switch_left = False
            list_window.switch_right = False

            if list_window_old:
                list_window_old.destroy()

            self.enable(False)
            list_window.messageLoop()
            result, mod = list_window.getResult()
            self.enable(True)

            if list_window.switch_left:
                pane = left_pane
            elif list_window.switch_right:
                pane = right_pane
            else:
                break

        self.activate()
        list_window.destroy()

        if result<0 : return
        if not list_items : return

        # Shift-Enter で決定したときは、ファイルリストに反映させる
        if mod==MODKEY_SHIFT:
            new_lister = cmailer_filelist.lister_Custom( self, pane.found_prefix, pane.found_location, pane.found_items )
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

            self.jumpLister( pane, cmailer_filelist.lister_Default(self,dirname), filename )

    ## アクティブではないペインと同じ場所に移動する
    #
    #  アクティブではないペインのカーソル位置のアイテムを調査し、
    #  そのアイテムが存在するディレクトリに移動した上で、同じアイテムにカーソルを合わせます。
    #
    def command_ChdirActivePaneToOther(self):
        active_pane = self.activePane()
        inactive_pane = self.inactivePane()
        cursor_item = inactive_pane.file_list.getItem(inactive_pane.cursor)

        lister, name = inactive_pane.file_list.getLister().getCopy(cursor_item.getName())
        self.jumpLister( active_pane, lister, name )

    ## アクティブではないペインのカレントディレクトリを、アクティブなペイント同じ場所に移動する
    #
    #  アクティブなペインのカーソル位置のアイテムを調査し、アクティブではないペインのカレントディレクトリを
    #  そのアイテムが存在するディレクトリに移動した上で、同じアイテムにカーソルを合わせます。
    #
    def command_ChdirInactivePaneToOther(self):
        active_pane = self.activePane()
        inactive_pane = self.inactivePane()
        cursor_item = active_pane.file_list.getItem(active_pane.cursor)

        lister, name = active_pane.file_list.getLister().getCopy(cursor_item.getName())
        self.jumpLister( inactive_pane, lister, name )

    ## 入力した名前でディレクトリを作成する
    #
    #  "1/2/3" のように、深いパスを入力することも出来ます。
    #   Shiftを押しながらディレクトリ名を決定すると、ディレクトリを作った後その中に移動します。
    #
    def command_Mkdir(self):
        pane = self.activePane()

        if not hasattr(pane.file_list.getLister(),"mkdir"):
            return

        result, mod = self.commandLine( u"MakeDir", auto_complete=False, autofix_list=["\\/","."], return_modkey=True, candidate_handler=cmailer_misc.candidate_Filename(pane.file_list.getLocation()) )
        if result==None : return

        newdirname = result

        self.subThreadCall( pane.file_list.getLister().mkdir, ( newdirname, sys.stdout.write ) )

        self.appendHistory( pane, True )
        
        if mod==MODKEY_SHIFT:
            self.activeJump(newdirname)
        else:
            self.subThreadCall( pane.file_list.refresh, () )
            pane.file_list.applyItems()
            pane.cursor = self.cursorFromName( pane.file_list, newdirname )
            pane.scroll_info.makeVisible( pane.cursor, self.fileListItemPaneHeight(), 1 )
            self.paint(PAINT_FOCUSED)

        print "Done.\n"

    ## ドライブを選択する
    def command_SelectDrive(self):
        pane = self.activePane()

        show_detail = [False]
        detail_mode = False

        def onKeyDown( vk, mod ):
            if vk==VK_SPACE and mod==0:
                show_detail[0] = True
                list_window.quit()
                return True

        while True:

            current_drive = os.path.splitdrive( pane.file_list.getLocation() )[0]
            initial_select = 0

            items = []
            items.append( "%s : %s" % ( "1", "Desktop" ) )
            for drive_letter in ckit.getDrives():
                
                if detail_mode:
                    drive_display_name = ckit.getDriveDisplayName( "%s:\\" % (drive_letter,) )
                    drive_display_name = drive_display_name.replace(" (%s:)"%drive_letter,"")
                    items.append( "%s : %s" % ( drive_letter, drive_display_name ) )
                else:                        
                    drive_display_type = ckit.getDriveType( "%s:\\" % (drive_letter,) )
                    items.append( "%s : %s" % ( drive_letter, drive_display_type ) )
                
                if current_drive and current_drive[0].upper()==drive_letter:
                    initial_select = len(items)-1

            if detail_mode:
                keydown_hook=None
            else:
                keydown_hook=onKeyDown    

            show_detail = [False]
            pos = self.centerOfFocusedPaneInPixel()
            list_window = cmailer_listwindow.ListWindow( pos[0], pos[1], 5, 1, self.width()-5, self.height()-3, self, self.ini, u"ドライブ選択", items, initial_select=initial_select, onekey_decide=True, keydown_hook=keydown_hook )
            self.enable(False)
            list_window.messageLoop()
            result = list_window.getResult()
            self.enable(True)
            self.activate()
            list_window.destroy()
            if show_detail[0]:
                detail_mode = True
                continue
            break

        if result<0 : return

        drive_letter = items[result][0]

        if drive_letter=='1':
            newdirname = ckit.getDesktopPath()
            lister = cmailer_filelist.lister_Default(self,newdirname)

        else:
            history_item = pane.history.findStartWith( "%s:" % drive_letter )
            if history_item==None :
                newdirname = "%s:\\" % drive_letter
            else:
                newdirname = history_item[0]
            lister = cmailer_filelist.lister_Default(self,newdirname)
            
        # 見つかるまで親ディレクトリを遡る
        def setListerAndGetParent(lister):
            while True:
                try:
                    pane.file_list.setLister(lister)
                    break
                except Exception, set_lister_error:
                    cmailer_debug.printErrorInfo()
                    try:
                        lister, child = lister.getParent()
                    except cmailer_error.NotExistError:
                        print u"移動失敗 : %s" % newdirname
                        print set_lister_error
                        return
                    except Exception, get_parent_error:
                        print u"移動失敗 : %s" % newdirname
                        print get_parent_error
                        return
            
            # 移動に成功したドライブに関して、存在しないブックマークを削除
            try:
                location = lister.getLocation()
                root_location = ckit.rootPath(location)
                self.bookmark.removeNotExists(root_location)
            except:
                cmailer_debug.printErrorInfo()

        self.subThreadCall( setListerAndGetParent, (lister,) )
        pane.file_list.applyItems()

        pane.scroll_info = ckit.ScrollInfo()
        pane.cursor = self.cursorFromHistory( pane.file_list, pane.history )
        pane.scroll_info.makeVisible( pane.cursor, self.fileListItemPaneHeight(), 1 )

        self.paint(PAINT_FOCUSED)

    ## インクリメンタルサーチを行う
    def command_IncrementalSearch(self):

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
                    self.command_Select()
                    cursorDown()
                elif mod==MODKEY_SHIFT:
                    self.command_Select()
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

    ## ファイル名検索を行う
    def command_Search(self):

        pane = self.activePane()

        location = pane.file_list.getLocation()
        if not os.path.isdir(location) : return

        result = self.commandLine( u"Search", candidate_handler=self.search_history.candidateHandler, candidate_remove_handler=self.search_history.candidateRemoveHandler )
        if result==None : return

        self.search_history.append(result)

        pattern = result
        pattern_list = pattern.split()

        items = []

        def jobSearch( job_item ):

            print u'Search : %s' % pattern

            # ビジーインジケータ On
            self.setProgressValue(None)
            
            filename_list = []

            for root, dirs, files in os.walk( location ):

                if job_item.isCanceled(): break
                
                if job_item.waitPaused():
                    self.setProgressValue(None)

                for name in files:
                    if job_item.isCanceled(): break

                    if job_item.waitPaused():
                        self.setProgressValue(None)

                    for pattern_item in pattern_list:
                        if fnmatch.fnmatch( name, pattern_item ):
                            path_from_here = ckit.normPath(os.path.join(root,name)[len(os.path.join(location,"")):])
                            print "  ", path_from_here
                            filename_list.append(path_from_here)
                            break

                for name in dirs:
                    if job_item.isCanceled(): break

                    if job_item.waitPaused():
                        self.setProgressValue(None)

                    for pattern_item in pattern_list:
                        if fnmatch.fnmatch( name, pattern_item ):
                            path_from_here = ckit.normPath(os.path.join(root,name)[len(os.path.join(location,"")):])
                            print "  ", path_from_here
                            filename_list.append(path_from_here)
                            break

            if job_item.isCanceled():
                print u'中断しました.\n'
            else:
                print u'Done.\n'

            def packListItem( filename ):
                if type(filename)==type(''):
                    filename = unicode(filename,'mbcs')

                item = cmailer_filelist.item_Default(
                    location,
                    filename
                    )

                return item

            items[:] = map( packListItem, filename_list )

            # ビジーインジケータ Off
            self.clearProgress()

        def jobSearchFinished( job_item ):
        
            if self.isQuitting() : return

            result = [ True ]

            def onKeyDown( vk, mod ):
                if vk==VK_RETURN and mod==0:
                    result[0] = True
                    console_window.quit()
                    return True
                elif vk==VK_ESCAPE and mod==0:
                    result[0] = False
                    console_window.quit()
                    return True

            pos = self.centerOfWindowInPixel()
            console_window = cmailer_consolewindow.ConsoleWindow( pos[0], pos[1], 60, 24, self, self.ini, u"Search完了", onKeyDown )
            self.enable(False)

            console_window.write( u'Search : %s\n' % pattern )
            for item in items:
                console_window.write( u'  %s\n' % item.getName(), False )
            console_window.write( u'\n' )
            console_window.write( u'検索結果をファイルリストに反映しますか？(Enter/Esc):\n' )

            console_window.messageLoop()
            self.enable(True)
            self.activate()
            console_window.destroy()

            if not result[0] : return

            prefix = u"[search] "
            new_lister = cmailer_filelist.lister_Custom( self, prefix, location, items )
            pane.file_list.setLister( new_lister )
            pane.file_list.applyItems()
            pane.scroll_info = ckit.ScrollInfo()
            pane.cursor = 0
            pane.scroll_info.makeVisible( pane.cursor, self.fileListItemPaneHeight(), 1 )
            pane.found_prefix = prefix
            pane.found_location = location
            pane.found_items = items
            self.paint( PAINT_LEFT | PAINT_RIGHT )

        job_item = ckit.JobItem( jobSearch, jobSearchFinished )
        self.taskEnqueue( job_item, u"Search" )

    ## GREPを行う
    def command_Grep(self):

        pane = self.activePane()

        location = pane.file_list.getLocation()
        if not os.path.isdir(location) : return

        item_filter = pane.file_list.getFilter()

        pos = self.centerOfWindowInPixel()
        grep_window = cmailer_grepwindow.GrepWindow( pos[0], pos[1], self, self.ini )
        self.enable(False)
        grep_window.messageLoop()
        result = grep_window.getResult()
        self.enable(True)
        self.activate()
        grep_window.destroy()

        if result==None : return
        pattern, recursive, regexp, ignorecase = result[0], result[1], result[2], result[3]

        # Grepのエンコーディングは、速度を考慮して、UTF-8限定
        pattern_utf8 = pattern.encode('utf-8')

        if regexp:
            try:
                if ignorecase:
                    re_pattern = re.compile( pattern_utf8, re.IGNORECASE )
                else:
                    re_pattern = re.compile( pattern_utf8 )
            except Exception, e:
                print u"正規表現のエラー :", e
                return []
        else:
            if ignorecase:
                pattern_utf8 = pattern_utf8.lower()

        items = []

        def jobGrep( job_item ):

            print u'Grep : %s' % pattern

            # ビジーインジケータ On
            self.setProgressValue(None)

            filename_list = []

            for root, dirs, files in os.walk( location ):

                if job_item.isCanceled(): break

                if job_item.waitPaused():
                    self.setProgressValue(None)

                if not recursive : del dirs[:]

                for filename in files:

                    if job_item.isCanceled(): break

                    if job_item.waitPaused():
                        self.setProgressValue(None)

                    if item_filter==None or item_filter( cmailer_filelist.item_Default(root,filename) ):

                        fullpath = os.path.join( root, filename )
                        
                        try:
                            fd = file( fullpath )

                            lineno = 0
                            for line in fd:
                                lineno += 1
                                hit = False
                                if regexp:
                                    if re_pattern.search(line):
                                        hit=True
                                else:

                                    if ignorecase:
                                        line = line.lower()

                                    if line.find(pattern_utf8)>=0:
                                        hit=True

                                if hit:
                                    path_from_here = ckit.normPath(fullpath[len(os.path.join(location,"")):])
                                    filename_list.append(path_from_here)
                                    print "  ", path_from_here
                                    break
                                    
                        except IOError, e:
                            print "  %s" % unicode(str(e),'mbcs')


            if job_item.isCanceled():
                print u'中断しました.\n'
            else:
                print u'Done.\n'

            def packListItem( filename ):
                if type(filename)==type(''):
                    filename = unicode(filename,'mbcs')

                item = cmailer_filelist.item_Default(
                    location,
                    filename
                    )

                return item

            items[:] = map( packListItem, filename_list )

            # ビジーインジケータ Off
            self.clearProgress()

        def jobGrepFinished( job_item ):

            if self.isQuitting() : return

            result = [ True ]

            def onKeyDown( vk, mod ):
                if vk==VK_RETURN and mod==0:
                    result[0] = True
                    console_window.quit()
                    return True
                elif vk==VK_ESCAPE and mod==0:
                    result[0] = False
                    console_window.quit()
                    return True

            pos = self.centerOfWindowInPixel()
            console_window = cmailer_consolewindow.ConsoleWindow( pos[0], pos[1], 60, 24, self, self.ini, u"Grep完了", onKeyDown )
            self.enable(False)

            console_window.write( u'Grep : %s\n' % pattern )
            for item in items:
                console_window.write( u'  %s\n' % item.getName(), False )
            console_window.write( u'\n' )
            console_window.write( u'Grepの結果をファイルリストに反映しますか？(Enter/Esc):\n' )

            console_window.messageLoop()
            self.enable(True)
            self.activate()
            console_window.destroy()

            if not result[0] : return

            prefix = u"[grep] "
            new_lister = cmailer_filelist.lister_Custom( self, prefix, location, items )
            pane.file_list.setLister( new_lister )
            pane.file_list.applyItems()
            pane.scroll_info = ckit.ScrollInfo()
            pane.cursor = 0
            pane.scroll_info.makeVisible( pane.cursor, self.fileListItemPaneHeight(), 1 )
            pane.found_prefix = prefix
            pane.found_location = location
            pane.found_items = items
            self.paint( PAINT_LEFT | PAINT_RIGHT )

        self.appendHistory( pane, True )

        job_item = ckit.JobItem( jobGrep, jobGrepFinished )
        self.taskEnqueue( job_item, u"Grep" )

    ## 選択アイテムの統計情報を出力する
    def command_Info(self):

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
            
            if not item.isdir():
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
            for item in items:
                if job_item.isCanceled(): break

                if job_item.waitPaused():
                    self.setProgressValue(None)

                if item.isdir():
                    dirname_len = self.getStringWidth(item.getName())
                    if max_dirname_len < dirname_len:
                        max_dirname_len = dirname_len

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

                if item.isdir():
                
                    total_stat.num_dirs += 1

                    stat = Stat()
            
                    for root, dirs, files in item.walk(False):
                    
                        if job_item.isCanceled(): break
                        
                        if job_item.waitPaused():
                            self.setProgressValue(None)

                        for dir in dirs:

                            if item_filter==None or item_filter(dir):
                                
                                total_stat.num_dirs += 1
                                stat.num_dirs += 1

                        for file in files:

                            if item_filter==None or item_filter(file):

                                total_stat.num_files += 1
                                stat.num_files += 1

                                total_stat.total_size += file.size()
                                stat.total_size += file.size()
                    
                    printStat( item.getName(), stat )

                else:

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
    def command_SetFilter(self):
        pane = self.activePane()

        result = self.commandLine( u"Filter", candidate_handler=self.pattern_history.candidateHandler, candidate_remove_handler=self.pattern_history.candidateRemoveHandler )
        if result==None : return
        
        self.pattern_history.append(result)

        self.subThreadCall( pane.file_list.setFilter, (cmailer_filelist.filter_Default( result, dir_policy=True ),) )
        pane.file_list.applyItems()
        pane.scroll_info = ckit.ScrollInfo()
        pane.cursor = self.cursorFromHistory( pane.file_list, pane.history )
        pane.scroll_info.makeVisible( pane.cursor, self.fileListItemPaneHeight(), 1 )
        self.paint(PAINT_FOCUSED)

    ## フィルタリストを表示し、フィルタを設定する
    def command_SetFilterList(self):
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
    def command_SelectUsingFilter(self):
        pane = self.activePane()

        result = self.commandLine( u"Select", candidate_handler=self.pattern_history.candidateHandler, candidate_remove_handler=self.pattern_history.candidateRemoveHandler )
        if result==None : return

        self.pattern_history.append(result)

        file_filter = cmailer_filelist.filter_Default( result, dir_policy=None )
        for i in xrange(pane.file_list.numItems()):
            item = pane.file_list.getItem(i)
            if file_filter(item):
                pane.file_list.selectItem( i, True )

        self.paint( PAINT_FOCUSED_ITEMS | PAINT_FOCUSED_HEADER )

    ## フィルタリストを表示し、合致するファイルを選択する
    def command_SelectUsingFilterList(self):
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

    ## 左右のペインで同じ名前のアイテムを選択する
    def command_SelectCompare(self):

        active_pane = self.activePane()
        inactive_pane = self.inactivePane()

        pos = self.centerOfFocusedPaneInPixel()
        list_window = cmailer_listwindow.ListWindow( pos[0], pos[1], 5, 1, self.width()-5, self.height()-3, self, self.ini, u"比較選択", self.compare_list, 0, onekey_decide=True )
        self.enable(False)
        list_window.messageLoop()
        result = list_window.getResult()
        self.enable(True)
        self.activate()
        list_window.destroy()

        if result<0 : return

        file_compare = self.compare_list[result][1]
        for i in xrange(active_pane.file_list.numItems()):
            active_item = active_pane.file_list.getItem(i)
            inactive_item = None
            for j in xrange(inactive_pane.file_list.numItems()):
                if active_item.getName().lower() == inactive_pane.file_list.getItem(j).getName().lower():
                    inactive_item = inactive_pane.file_list.getItem(j)
                    break
            if not inactive_item : continue

            if file_compare( active_item, inactive_item ):
                active_pane.file_list.selectItem( i, True )

        self.paint( PAINT_FOCUSED_ITEMS | PAINT_FOCUSED_HEADER )

    ## 比較機能の選択リストを表示する
    def command_CompareTools(self):
        result = cmailer_listwindow.popMenu( self, u"比較ツール", self.compare_tool_list, 0 )
        if result<0 : return
        self.compare_tool_list[result][1]()

    ## 選択された２つのファイルアイテムを比較する
    def command_Diff(self):
    
        import cmailer_diffviewer
    
        pane = self.activePane()
        location = pane.file_list.getLocation()

        items = []
        for i in xrange(self.left_pane.file_list.numItems()):
            item = self.left_pane.file_list.getItem(i)
            if item.selected():
                items.append(item)

        for i in xrange(self.right_pane.file_list.numItems()):
            item = self.right_pane.file_list.getItem(i)
            if item.selected():
                items.append(item)
        
        if len(items)<2:
            cmailer_msgbox.popMessageBox( self, MessageBox.TYPE_OK, u"ファイル比較", u"ファイルを２つ選択してください。" )
            return
        elif len(items)>2:
            cmailer_msgbox.popMessageBox( self, MessageBox.TYPE_OK, u"ファイル比較", u"ファイルを２つだけ選択してください。" )
            return

        fd = [ None, None ]
        fd[0] = items[0].open()
        fd[1] = items[1].open()

        data_64kb = [ None, None ]
        data_64kb[0] = fd[0].read( 64 * 1024 )
        data_64kb[1] = fd[1].read( 64 * 1024 )
        
        encoding = [ None, None ]

        text_encoding = ckit.detectTextEncoding(data_64kb[0])
        encoding[0] = text_encoding.encoding

        text_encoding = ckit.detectTextEncoding(data_64kb[1])
        encoding[1] = text_encoding.encoding

        def printFilenameLog( str_mode ):
            print u"ファイル比較 (%s):" % str_mode
            print u"   left ;", items[0].getName()
            print u"  right ;", items[1].getName()

        if encoding[0]==None or encoding[1]==None:
            
            if items[0].size() != items[1].size() or data_64kb[0] != data_64kb[1]:
                printFilenameLog( "binary" )
                cmailer_msgbox.popMessageBox( self, MessageBox.TYPE_OK, u"ファイル比較", u"ファイルの内容には差異があります。" )
                print u'Done.\n'
                return

            result = [None]

            def jobCompareBinaryFile(job_item):

                printFilenameLog( "binary" )

                # ビジーインジケータ On
                self.setProgressValue(None)

                if result[0]==None and hasattr( items[0], "getFullpath" ) and hasattr( items[1], "getFullpath" ):
                    try:
                        result[0] = cmailer_filecmp.compareFile( items[0].getFullpath(), items[1].getFullpath(), schedule_handler=job_item.isCanceled )
                    except cmailer_error.CanceledError:
                        return
                    
                if result[0]==None:
                    while True:
                        if job_item.isCanceled() : break

                        if job_item.waitPaused():
                            self.setProgressValue(None)

                        data0 = fd[0].read( 64 * 1024 )
                        data1 = fd[1].read( 64 * 1024 )
                        if not data0 and not data1 :
                            result[0] = True
                            break
                        if data0!=data1 :
                            result[0] = False
                            break

            def jobCompareBinaryFileFinished(job_item):

                # ビジーインジケータ Off
                self.clearProgress()

                if not job_item.isCanceled():
                    if result[0]:
                        cmailer_msgbox.popMessageBox( self, MessageBox.TYPE_OK, u"ファイル比較", u"ファイルの内容は同一です。" )
                    else:
                        cmailer_msgbox.popMessageBox( self, MessageBox.TYPE_OK, u"ファイル比較", u"ファイルの内容には差異があります。" )

                if job_item.isCanceled():
                    print u'中断しました.\n'
                else:
                    print u'Done.\n'

            job_item = ckit.JobItem( jobCompareBinaryFile, jobCompareBinaryFileFinished )
            self.taskEnqueue( job_item, u"CompareBinary" )

        else:
        
            printFilenameLog( "text" )
    
            def onEdit():
                if not hasattr(items[0],"getFullpath") or not hasattr(items[1],"getFullpath") : return
                if self.diff_editor==None : return
                viewer.destroy()
                if callable(self.diff_editor):
                    self.diff_editor( items[0], items[1], location )
                else:
                    self.subThreadCall( ckit.shellExecute, ( None, None, self.diff_editor, '"%s" "%s"'% ( items[0].getFullpath(), items[1].getFullpath() ), location ) )

            pos = self.centerOfWindowInPixel()
            viewer = cmailer_diffviewer.DiffViewer( pos[0], pos[1], self.width(), self.height(), self, self.ini, u"diff", items[0], items[1], edit_handler=onEdit )
            print u'Done.\n'

    ## 左右のディレクトリを比較する
    def command_DirCompare(self):

        left_pane = self.left_pane
        right_pane = self.right_pane
        
        left_location = left_pane.file_list.getLocation()
        right_location = right_pane.file_list.getLocation()

        for path in ( left_location, right_location ):
            if not os.path.isdir(path):
                print u"ディレクトリ比較が不可能なパス :", path
                return

        compare_list = [
            ( u"C : 両方に存在",      u"両方に存在",      ( True,  None ) ),
            ( u"O : 片方だけに存在",  u"片方だけに存在",  ( False, None ) ),
            ( u"S : 内容が同じ",      u"内容が同じ",      ( None,  True ) ),
            ( u"D : 内容が相違",      u"内容が相違",      ( None,  False ) ),
            ( u"M : 片方または相違",  u"片方または相違",  ( False, False ) ),
        ]

        pos = self.centerOfWindowInPixel()
        list_window = cmailer_listwindow.ListWindow( pos[0], pos[1], 5, 1, self.width()-5, self.height()-3, self, self.ini, u"ディレクトリ比較", compare_list, 0, onekey_decide=True )
        self.enable(False)
        list_window.messageLoop()
        result = list_window.getResult()
        self.enable(True)
        self.activate()
        list_window.destroy()

        if result<0 : return

        compare_name = compare_list[result][1]
        select_common, select_same = compare_list[result][2]

        left_items = []
        right_items = []
        
        def jobCompare( job_item ):

            print u'Compare : %s' % compare_name

            # ビジーインジケータ On
            self.setProgressValue(None)

            def packListItem( location, filename ):
                if type(filename)==type(''):
                    filename = unicode(filename,'mbcs')
                item = cmailer_filelist.item_Default(
                    location,
                    filename
                    )
                return item

            def dump_compare( cmp, dirname ):

                #print dirname, dirname, cmp.left_only

                if select_common==True:

                    for filename in cmp.common_files:
                        if job_item.isCanceled() : return

                        if job_item.waitPaused():
                            self.setProgressValue(None)

                        name = ckit.normPath(ckit.joinPath(dirname,filename))
                        print "      Common :", name
                        left_items.append( packListItem( left_location, name ) )
                        right_items.append( packListItem( right_location, name ) )

                elif select_common==False:

                    for filename in cmp.left_only:
                        if job_item.isCanceled() : return

                        if job_item.waitPaused():
                            self.setProgressValue(None)

                        name = ckit.normPath(ckit.joinPath(dirname,filename))
                        print "   Left Only :", name
                        left_items.append( packListItem( left_location, name ) )

                    for filename in cmp.right_only:
                        if job_item.isCanceled() : return

                        if job_item.waitPaused():
                            self.setProgressValue(None)

                        name = ckit.normPath(ckit.joinPath(dirname,filename))
                        print "  Right Only :", name
                        right_items.append( packListItem( right_location, name ) )

                if select_same==True:

                    for filename in cmp.same_files:
                        if job_item.isCanceled() : return

                        if job_item.waitPaused():
                            self.setProgressValue(None)

                        name = ckit.normPath(ckit.joinPath(dirname,filename))
                        print "        Same :", name
                        left_items.append( packListItem( left_location, name ) )
                        right_items.append( packListItem( right_location, name ) )

                elif select_same==False:

                    for filename in cmp.diff_files:
                        if job_item.isCanceled() : return

                        if job_item.waitPaused():
                            self.setProgressValue(None)

                        name = ckit.normPath(ckit.joinPath(dirname,filename))
                        print "      Differ :", name
                        left_items.append( packListItem( left_location, name ) )
                        right_items.append( packListItem( right_location, name ) )

                for subdirname in cmp.common_dirs:
                    if job_item.isCanceled() : return

                    if job_item.waitPaused():
                        self.setProgressValue(None)

                    dump_compare( cmp.subdirs[subdirname], ckit.joinPath(dirname,subdirname) )

            cmp = cmailer_filecmp.CompareDir( left_location, right_location, [], [] )
            
            try:
                dump_compare( cmp, "" )
            except Exception, e:
                print u'ERROR : ディレクトリ比較に失敗'
                print u"  %s" % unicode(str(e),'mbcs')
                cmailer_debug.printErrorInfo()
                job_item.cancel()

            if job_item.isCanceled():
                print u'中断しました.\n'
            else:
                print u'Done.\n'

            # ビジーインジケータ Off
            self.clearProgress()

        def jobCompareFinished( job_item ):

            if self.isQuitting() : return

            result = [ True ]

            def onKeyDown( vk, mod ):
                if vk==VK_RETURN and mod==0:
                    result[0] = True
                    console_window.quit()
                    return True
                elif vk==VK_ESCAPE and mod==0:
                    result[0] = False
                    console_window.quit()
                    return True

            pos = self.centerOfWindowInPixel()
            console_window = cmailer_consolewindow.ConsoleWindow( pos[0], pos[1], 60, 24, self, self.ini, u"Compare完了", onKeyDown )
            self.enable(False)

            console_window.write( u'Compare : %s\n\n' % compare_name )

            console_window.write( u'Left:\n' )
            for item in left_items:
                console_window.write( u'  %s\n' % item.getName(), False )
            console_window.write( u'\n' )

            console_window.write( u'Right:\n' )
            for item in right_items:
                console_window.write( u'  %s\n' % item.getName(), False )
            console_window.write( u'\n' )

            console_window.write( u'比較結果をファイルリストに反映しますか？(Enter/Esc):\n' )

            console_window.messageLoop()
            self.enable(True)
            self.activate()
            console_window.destroy()

            if not result[0] : return

            left_lister = cmailer_filelist.lister_Custom( self, u"[compare] ", left_location, left_items )
            left_pane.file_list.setLister( left_lister )
            left_pane.file_list.applyItems()
            left_pane.scroll_info = ckit.ScrollInfo()
            left_pane.cursor = 0
            left_pane.scroll_info.makeVisible( left_pane.cursor, self.fileListItemPaneHeight(), 1 )

            right_lister = cmailer_filelist.lister_Custom( self, u"[compare] ", right_location, right_items )
            right_pane.file_list.setLister( right_lister )
            right_pane.file_list.applyItems()
            right_pane.scroll_info = ckit.ScrollInfo()
            right_pane.cursor = 0
            right_pane.scroll_info.makeVisible( left_pane.cursor, self.fileListItemPaneHeight(), 1 )

            self.paint( PAINT_LEFT | PAINT_RIGHT )

        self.appendHistory( left_pane, True )
        self.appendHistory( right_pane, True )

        job_item = ckit.JobItem( jobCompare, jobCompareFinished )
        self.taskEnqueue( job_item, u"Compare" )

    ## ソートポリシーを設定する
    def command_SetSorter(self):
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

    ## アイテムのファイル名やタイムスタンプなどを変更する
    #
    #  アイテムが１つも選択されていないときと、そうでないときとで挙動が異なります。\n\n
    #  アイテムが選択されていないとき、カーソル位置のアイテムの、ファイル名、タイムスタンプ、ファイル属性を変更するダイアログがポップアップします。\n\n
    #  アイテムが選択されているとき、選択されているアイテムの、タイムスタンプ、ファイル属性を変更するダイアログがポップアップします。
    #
    def command_Rename(self):

        pane = self.activePane()

        items = []
        for i in xrange(pane.file_list.numItems()):
            item = pane.file_list.getItem(i)
            if item.selected() and hasattr(item,"rename") and hasattr(item,"utime") and hasattr(item,"uattr"):
                items.append(item)

        if not pane.file_list.selected():

            item = pane.file_list.getItem(pane.cursor)

            if not (hasattr(item,"rename") and hasattr(item,"utime") and hasattr(item,"uattr")):
                return

            pos = self.centerOfFocusedPaneInPixel()
            rename_window = cmailer_renamewindow.RenameWindow( pos[0], pos[1], self, self.ini, item )
            self.enable(False)
            rename_window.messageLoop()
            result = rename_window.getResult()
            self.enable(True)
            self.activate()
            rename_window.destroy()

            if result==None : return
            new_filename, new_timestamp, new_attribute = result[0], result[1], result[2]

            new_filename = os.path.join( os.path.split( item.getName())[0], new_filename )
            if new_filename!=item.getName():
                print u'名前変更 : %s -> %s …' % (item.getName(), new_filename),
                try:
                    item.rename( new_filename )
                except:
                    print u'失敗'
                    cmailer_debug.printErrorInfo()
                    return
                print u'完了'

            old_timestamp = item.time()
            if new_timestamp!=old_timestamp:
                print u'タイムスタンプ変更 : %s …' % (new_filename),
                try:
                    item.utime((
                        new_timestamp[0],
                        new_timestamp[1],
                        new_timestamp[2],
                        new_timestamp[3],
                        new_timestamp[4],
                        new_timestamp[5]
                        ))
                except:
                    print u'失敗'
                    cmailer_debug.printErrorInfo()
                else:
                    print u'完了'

            old_attribute = item.attr()
            old_attribute &= (
                ckit.FILE_ATTRIBUTE_READONLY |
                ckit.FILE_ATTRIBUTE_SYSTEM |
                ckit.FILE_ATTRIBUTE_HIDDEN |
                ckit.FILE_ATTRIBUTE_ARCHIVE
                )

            if new_attribute!=old_attribute:
                print u'属性変更 : %s …' % (new_filename),
                try:
                    item.uattr( new_attribute )
                except:
                    print u'失敗'
                    cmailer_debug.printErrorInfo()
                else:
                    print u'完了'

            print u'Done.\n'

            self.appendHistory( pane, True )

            self.refreshFileList( self.left_pane, True, True )
            self.refreshFileList( self.right_pane, True, True )
            self.paint( PAINT_LEFT | PAINT_RIGHT )

        else:

            if len(items)<=0 : return

            pos = self.centerOfFocusedPaneInPixel()
            rename_window = cmailer_renamewindow.MultiRenameWindow( pos[0], pos[1], self, self.ini, items )
            self.enable(False)
            rename_window.messageLoop()
            result = rename_window.getResult()
            self.enable(True)
            self.activate()
            rename_window.destroy()

            if result==None : return
            recursive, new_timestamp, new_case, new_attribute = result[0], result[1], result[2], result[3]
            new_allcase, new_extcase = new_case[0], new_case[1]
            new_readonly, new_system, new_hidden, new_archive = new_attribute[0], new_attribute[1], new_attribute[2], new_attribute[3]

            class jobModifyInfo:

                def __init__(job_self):
                    pass

                def updateFileInfo( job_self, item ):
                
                    if new_allcase!=1 or new_extcase!=1:
                        
                        body, ext = os.path.splitext(item.getName())

                        if new_allcase==0:
                            body = body.lower()
                            ext = ext.lower()
                        elif new_allcase==2:
                            body = body.upper()
                            ext = ext.upper()

                        if new_extcase==0:
                            ext = ext.lower()
                        elif new_extcase==2:
                            ext = ext.upper()

                        new_filename = body + ext

                        if new_filename!=item.getName():
                            print u'名前変更 : %s -> %s …' % (item.getName(), new_filename),
                            try:
                                item.rename( new_filename )
                            except:
                                print u'失敗'
                                cmailer_debug.printErrorInfo()
                                return
                            print u'完了'

                    if new_timestamp:
                        print u'タイムスタンプ変更 : %s …' % item.getName(),
                        try:
                            item.utime((
                                new_timestamp[0],
                                new_timestamp[1],
                                new_timestamp[2],
                                new_timestamp[3],
                                new_timestamp[4],
                                new_timestamp[5]
                                ))
                        except:
                            print u'失敗'
                            cmailer_debug.printErrorInfo()
                        else:
                            print u'完了'

                    attribute = item.attr()

                    if new_readonly==0 : attribute &= ~ckit.FILE_ATTRIBUTE_READONLY
                    elif new_readonly==2 : attribute |= ckit.FILE_ATTRIBUTE_READONLY

                    if new_system==0 : attribute &= ~ckit.FILE_ATTRIBUTE_SYSTEM
                    elif new_system==2 : attribute |= ckit.FILE_ATTRIBUTE_SYSTEM

                    if new_hidden==0 : attribute &= ~ckit.FILE_ATTRIBUTE_HIDDEN
                    elif new_hidden==2 : attribute |= ckit.FILE_ATTRIBUTE_HIDDEN

                    if new_archive==0 : attribute &= ~ckit.FILE_ATTRIBUTE_ARCHIVE
                    elif new_archive==2 : attribute |= ckit.FILE_ATTRIBUTE_ARCHIVE

                    print u'属性変更 : %s …' % item.getName(),
                    try:
                        item.uattr( attribute )
                    except:
                        print u'失敗'
                        cmailer_debug.printErrorInfo()
                    else:
                        print u'完了'

                def __call__( job_self, job_item ):

                    # ビジーインジケータ On
                    self.setProgressValue(None)

                    for item in items:

                        if job_item.isCanceled(): break

                        if item.isdir():
                            if recursive:
                                for root, dirs, files in item.walk():
                                    for file in files:
                                        job_self.updateFileInfo( file )
                        else:
                            job_self.updateFileInfo(item)

            def jobModifyInfoFinished(job_item):

                # ビジーインジケータ Off
                self.clearProgress()

                if job_item.isCanceled():
                    print u'中断しました.\n'
                else:
                    print "Done.\n"

                self.refreshFileList( self.left_pane, True, True )
                self.refreshFileList( self.right_pane, True, True )
                self.paint( PAINT_LEFT | PAINT_RIGHT )

            self.appendHistory( pane, True )

            job_item = ckit.JobItem( jobModifyInfo(), jobModifyInfoFinished )
            self.taskEnqueue( job_item, u"ファイル情報の変更" )

    ## 一括リネームする
    def command_BatchRename(self):

        pane = self.activePane()

        items = []
        for i in xrange(pane.file_list.numItems()):
            item = pane.file_list.getItem(i)
            if item.selected() and hasattr(item,"rename"):
                items.append(item)

        if len(items)<=0 : return

        pos = self.centerOfWindowInPixel()
        batch_rename_window = cmailer_renamewindow.BatchRenameWindow( pos[0], pos[1], self, self.ini, items )
        self.enable(False)
        batch_rename_window.messageLoop()
        result = batch_rename_window.getResult()
        self.enable(True)
        self.activate()
        batch_rename_window.destroy()

        if result==None : return
        replace_before, replace_after, regexp, ignorecase = result[0], result[1], result[2], result[3]
        
        if len(replace_before)==0:
            print u"ERROR : 置換前の文字列が未入力"
            return

        confirm = [ True ]

        self.ini.set( "BATCHRENAME", "old", replace_before )
        self.ini.set( "BATCHRENAME", "new", replace_after )
        self.ini.set( "BATCHRENAME", "regexp", str(int(regexp)) )
        self.ini.set( "BATCHRENAME", "ignorecase", str(int(ignorecase)) )

        def onKeyDown( vk, mod ):
            if vk==VK_RETURN and mod==0:
                confirm[0] = True
                console_window.quit()
                return True
            elif vk==VK_ESCAPE and mod==0:
                confirm[0] = False
                console_window.quit()
                return True

        class Rename:

            def __init__( self, regexp, ignorecase, old, new, maxnum ):

                self.regexp = regexp
                self.ignorecase = ignorecase
                self.old = old
                self.new = new
                self.number = 0
                self.keta = math.log10(maxnum)+1

                if self.regexp:
                    if self.ignorecase:
                        self.re_pattern = re.compile( self.old, re.IGNORECASE )
                    else:
                        self.re_pattern = re.compile( self.old )
                else:
                    self.re_pattern = None

            def __call__(self,old_name):

                new_name = u""

                if self.regexp:
                    re_result = self.re_pattern.match(old_name)
                    if re_result and re_result.group(0)==old_name:
                        pos = 0
                        while pos<len(self.new):
                            if self.new[pos]==u'\\' and pos+1<len(self.new):
                                pos += 1
                                if self.new[pos] in ( u'0', u'1', u'2', u'3', u'4', u'4', u'5', u'6', u'7', u'8', u'9' ):
                                    new_name += re_result.group( int(self.new[pos]) )
                                elif self.new[pos] == u'd':
                                    fmt = "%0" + ("%d"%self.keta) + "d"
                                    new_name += fmt % self.number
                                elif old_name[pos]=='\\':
                                    new_name += '\\'
                            else:
                                new_name += self.new[pos]
                            pos += 1
                    else:
                        new_name = old_name
                else:
                    if self.ignorecase:
                        old_name_lower = old_name.lower()
                        old_lower = self.old.lower()
                        pos = 0
                        while pos<len(old_name):
                            find_result = old_name_lower.find(old_lower,pos)
                            if find_result>=0:
                                new_name += old_name[ pos : find_result ]
                                new_name += self.new
                                pos = find_result + len(old_lower)
                            else:
                                new_name += old_name[ pos : ]
                                break
                    else:
                        new_name = old_name.replace( self.old, self.new )
                self.number += 1
                return new_name

            def resetNumbar(self):
                self.number = 0

        try:
            rename = Rename( regexp, ignorecase, replace_before, replace_after, len(items) )
        except re.error, e:
            print u"正規表現のエラー :", e
            return    

        pos = self.centerOfWindowInPixel()
        console_window = cmailer_consolewindow.ConsoleWindow( pos[0], pos[1], 60, 24, self, self.ini, u"変名の確認", onKeyDown )
        self.enable(False)

        console_window.write( u'一括変名:\n' )
        for item in items:
            old_name = item.getName()
            new_name = rename(old_name)
            if old_name != new_name:
                console_window.write( u'  %s -> %s\n' % (old_name, new_name), False )
            else:
                console_window.write( u'  %s : 変更なし\n' % (old_name,), False )
        console_window.write( u'\n' )
        console_window.write( u'実行しますか？(Enter/Esc):\n' )

        console_window.messageLoop()
        self.enable(True)
        self.activate()
        console_window.destroy()

        if not confirm[0] : return

        rename.resetNumbar()

        def jobBatchRename(job_item):

            # ビジーインジケータ On
            self.setProgressValue(None)

            print u'一括変名:'
            for item in items:

                if job_item.isCanceled() : break

                old_name = item.getName()
                new_name = rename(old_name)
                if old_name != new_name:
                    print u'  %s -> %s …' % (old_name, new_name),
                    try:
                        item.rename(new_name)
                    except:
                        print u'失敗'
                        cmailer_debug.printErrorInfo()
                        job_item.cancel()
                        break
                    print u'完了'
                else:
                    print u'  %s … 変更なし' % (old_name,)

        def jobBatchRenameFinished(job_item):

            # ビジーインジケータ Off
            self.clearProgress()

            if job_item.isCanceled():
                print u'中断しました.\n'
            else:
                print "Done.\n"

            self.refreshFileList( self.left_pane, True, True )
            self.refreshFileList( self.right_pane, True, True )
            self.paint( PAINT_LEFT | PAINT_RIGHT )

        self.appendHistory( pane, True )

        job_item = ckit.JobItem( jobBatchRename, jobBatchRenameFinished )
        self.taskEnqueue( job_item, u"一括変名" )

    ## コンテキストメニューをポップアップする
    def command_ContextMenu(self):
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
    def command_ContextMenuDir(self):
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
    def command_Quit(self):

        if self.ini.getint("MISC","confirm_quit"):
            result = cmailer_msgbox.popMessageBox( self, MessageBox.TYPE_YESNO, u"終了確認", u"%sを終了しますか？" % cmailer_resource.cmailer_appname )
            if result!=MessageBox.RESULT_YES : return

        self.quit()

    ## 次のCraftMailerに切り替える
    def command_ActivateCmailerNext(self):
    
        desktop = pyauto.Window.getDesktop()
        wnd = desktop.getFirstChild()
        last_found = None
        while wnd:
            if wnd.getClassName()=="CmailerWindowClass":
                last_found = wnd
            wnd = wnd.getNext()
        if last_found:
            wnd = last_found.getLastActivePopup()
            wnd.setForeground()

    def _viewCommon( self, location, item ):
        if not item.isdir() and hasattr(item,"open"):

            if item.size() >= 32*1024*1024:
                result = cmailer_msgbox.popMessageBox( self, MessageBox.TYPE_YESNO, u"大きなファイルの閲覧", u"大きなファイルを閲覧しますか？(時間がかかる場合があります)" )
                if result!=MessageBox.RESULT_YES : return

            def onEdit():
                if not hasattr(item,"getFullpath") : return
                scroll_pos = viewer.getVisibleRegion()
                viewer.destroy()
                if callable(self.editor):
                    self.subThreadCall( self.editor, ( item, ( scroll_pos[0], scroll_pos[1] ), location ) )
                else:
                    self.subThreadCall( ckit.shellExecute, ( None, None, self.editor, '"%s"'%item.getFullpath(), location ) )

            pos = self.centerOfWindowInPixel()
            viewer = cmailer_textviewer.TextViewer( pos[0], pos[1], self.width(), self.height(), self, self.ini, u"text viewer", item, edit_handler=onEdit )

    ## テキストビューアまたはバイナリビューアでファイルを閲覧する
    def command_View(self):
        pane = self.activePane()
        location = pane.file_list.getLocation()
        item = pane.file_list.getItem(pane.cursor)
        self._viewCommon( location, item )

    ## ログペインの選択範囲またはアイテムのファイル名をクリップボードにコピーする
    #
    #  ログペインのテキストが選択されている場合は、その選択範囲をクリップボードに格納します。
    #  ログペインのテキストが選択されていない場合は、アイテムのファイル名をクリップボードに格納します。
    #
    def command_SetClipboard_LogSelectedOrFilename(self):
        selection_left, selection_right = self.log_pane.selection
        if selection_left != selection_right:
            self.command_SetClipboard_LogSelected()
        else:
            self.command_SetClipboard_Filename()

    ## アイテムのファイル名をクリップボードにコピーする
    #
    #  アイテムが選択されているときは、選択されている全てのアイテムのファイル名を、改行区切りで連結してクリップボードに格納します。
    #  アイテムが選択されていないときは、カーソル位置のファイル名をクリップボードに格納します。
    #
    def command_SetClipboard_Filename(self):
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

        self.command_DeselectAll()

        self.setStatusMessage( u"ファイル名をクリップボードにコピーしました", 3000 )

    ## アイテムのファイル名をフルパスでクリップボードにコピーする
    #
    #  アイテムが選択されているときは、選択されている全てのアイテムのフルパスを、改行区切りで連結してクリップボードに格納します。
    #  アイテムが選択されていないときは、カーソル位置のファイルのフルパスをクリップボードに格納します。
    #
    def command_SetClipboard_Fullpath(self):
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

        self.command_DeselectAll()

        self.setStatusMessage( u"フルパスをクリップボードにコピーしました", 3000 )

    ## ログペインの選択範囲をクリップボードにコピーする
    def command_SetClipboard_LogSelected(self):

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
    def command_SetClipboard_LogAll(self):
        lines = []
        for i in xrange(self.log_pane.log.numLines()):
            lines.append( self.log_pane.log.getLine(i) )
        ckit.setClipboardText( '\r\n'.join(lines) )

        self.log_pane.selection = [ [ 0, 0 ], [ 0, 0 ] ]
        self.paint(PAINT_LOG)

        self.setStatusMessage( u"全てのログをクリップボードにコピーしました", 3000 )

    ## カーソル位置のアイテムをブックマークに登録するか解除する
    def command_Bookmark(self):

        pane = self.activePane()

        item = pane.file_list.getItem(pane.cursor)
        if not hasattr(item,"getFullpath"): return

        dirname, filename = ckit.splitPath(item.getFullpath())

        if self.bookmark.listDir(dirname).has_key(filename.lower()):
            self.bookmark.remove( item.getFullpath() )
        else:
            self.bookmark.append( item.getFullpath() )

        self.refreshFileList( self.activePane(), True, True )
        self.refreshFileList( self.inactivePane(), True, True )
        self.paint( PAINT_LEFT | PAINT_RIGHT )

    def _bookmarkListCommon( self, local ):

        pane = self.activePane()

        items = self.bookmark.getItems()
        
        if local:
            location_lower = pane.file_list.getLocation().lower()
            
            def isLocalBookmark(item):
                if len(item)>len(location_lower) and item.lower().startswith(location_lower):
                    if location_lower[-1] in "\\/" or item[len(location_lower)] in "\\/":
                        return True
                return False        
            
            items = filter( isLocalBookmark, items )

        if not len(items):
            self.setStatusMessage( u"ブックマークがありません", 1000, error=True )
            return

        if local:
            items = map( lambda item : (item[len(location_lower):].lstrip('\\/'),item), items )
        else:
            items = map( lambda item : (item,item), items )

        def onKeyDown( vk, mod ):
            if vk==VK_DELETE and mod==0:

                select = list_window.getResult()
                self.bookmark.remove(items[select][1])
                list_window.remove(select)

                self.refreshFileList( pane, True, True )
                self.paint(PAINT_FOCUSED)

                return True

        if local:
            title = u"Bookmark (Local)"
        else:
            title = u"Bookmark (Global)"

        def onStatusMessage( width, select ):
            return u""

        pos = self.centerOfWindowInPixel()
        list_window = cmailer_listwindow.ListWindow( pos[0], pos[1], 5, 1, self.width()-5, self.height()-3, self, self.ini, title, items, initial_select=0, keydown_hook=onKeyDown, onekey_search=False, statusbar_handler=onStatusMessage )
        self.enable(False)
        list_window.messageLoop()
        result = list_window.getResult()
        self.enable(True)
        self.activate()
        list_window.destroy()

        if result<0 : return
        
        if local:
            fullpath = ckit.joinPath( pane.file_list.getLocation(), items[result][0] )
        else:
            fullpath = items[result][0]

        self.bookmark.append(fullpath)
        dirname, filename = ckit.splitPath(fullpath)

        self.jumpLister( pane, cmailer_filelist.lister_Default(self,dirname), filename )

    ## ブックマークの一覧を表示する(グローバル)
    #
    #  登録されている全てのブックマークを一覧表示します。
    #
    def command_BookmarkList(self):
        self._bookmarkListCommon(False)

    ## ブックマークの一覧を表示する(ローカル)
    #
    #  カレントディレクトリ以下のブックマークを一覧表示します。
    #
    def command_BookmarkListLocal(self):
        self._bookmarkListCommon(True)

    def command_ReceiveTest(self):

        print "ReceiveTest"

        count = 0

        self.inbox_folder.lock()

        try:
            for email in self.account.receive():
                print email.subject, time.strftime( "%Y/%m/%d %H:%M:%S", email.date )
                self.inbox_folder.add(email)
                count += 1
                if count >= 10 : break
            self.inbox_folder.flush()
        finally:
            self.inbox_folder.unlock()

        print "ReceiveTest end"

    ## Pythonインタプリタのメモリの統計情報を出力する(デバッグ目的)
    def command_MemoryStat(self):
        
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
    def command_RefererTree( self, args ):
    
        kwd = args[0]
    
        max_depth = 5
        if len(args)>1:
            max_depth = int(args[1])
    
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
    def command_CommandLine(self):

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
    def command_Wallpaper(self):
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
    def command_ConfigMenu(self):
        cmailer_configmenu.doConfigMenu( self )

    ## 設定メニュー2をポップアップする
    #
    #  設定メニュー2には、普段の使用で、頻繁には変更しないものが入っています。
    #
    def command_ConfigMenu2(self):
        cmailer_configmenu.doConfigMenu2( self )

    ## 設定スクリプトをリロードする
    def command_Reload(self):
        self.configure()
        print u"設定スクリプトをリロードしました.\n"

    ## メーラのバージョン情報を出力する
    def command_About(self):
        print cmailer_resource.startupString()

#--------------------------------------------------------------------

## @} mainwindow
