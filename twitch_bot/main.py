from PyQt4 import QtGui, QtCore
import sys, os
from cStringIO import StringIO
import subprocess
import yaml

import hue_bot
import phue
import config
import hue_retry_box
from twitch_irc import TwitchIrc
from log import get_logger
from version import package_version

from updater4pyi import upd_source, upd_core, upd_log, upd_downloader
from updater4pyi.upd_iface_pyqt4 import UpdatePyQt4Interface

from multiprocessing import Process, Queue, Manager
if sys.platform == 'win32':
    import multiprocessing.reduction    # make sockets pickable/inheritable

logger = get_logger(__name__)

# The new Stream Object which replaces the default stream associated with sys.stdout
# This object just puts data in a queue!
class WriteStream(object):
  def __init__(self,queue):
    self.queue = queue

  def write(self, text):
    self.queue.put(text)

  def flush(self):
    pass

# A QObject (to be run in a QThread) which sits waiting for data to come through a Queue.Queue().
# It blocks until data is available, and one it has got something from the queue, it sends
# it to the "MainThread" by emitting a Qt Signal
class MyReceiver(QtCore.QObject):
  mysignal = QtCore.pyqtSignal(str)

  def __init__(self,queue,*args,**kwargs):
    QtCore.QObject.__init__(self,*args,**kwargs)
    self.queue = queue

  @QtCore.pyqtSlot()
  def run(self):
    while True:
      text = self.queue.get()
      self.mysignal.emit(text)

class ConfigWindow(QtGui.QDialog, config.Ui_Dialog):
  def __init__(self, parent=None):
    super(ConfigWindow, self).__init__(parent)
    self.setupUi(self)

    self.button_box.button(QtGui.QDialogButtonBox.Save).clicked.connect(self.save)
    self.button_box.button(QtGui.QDialogButtonBox.Close).clicked.connect(self.close)
    self.button_box.button(QtGui.QDialogButtonBox.Reset).clicked.connect(self.reset)

    self.load()

  def load(self):
    config = {}
    if os.path.isfile("config.yml"):
      with open("config.yml", 'r') as config_file:
        config = yaml.load(config_file) or {}

    if config:
      if 'username' in config:
        self.username_textbox.setText(config['username'])
      if 'oauth' in config:
        self.oauth_textbox.setText(config['oauth'])
      if 'admin-user' in config:
        self.admin_textbox.setText(config['admin-user'])
      if 'channel' in config:
        self.channel_textbox.setText(config['channel'])
      if 'hue-bridge-group' in config:
        self.hue_group_textbox.setText(config['hue-bridge-group'])
      if 'hue-bridge-ip' in config:
        self.hue_ip_textbox.setText(config['hue-bridge-ip'])
      if 'hue-color-end' in config:
        self.color_end_textbox.setText(str(config['hue-color-end']))
      if 'hue-color-start' in config:
        self.color_start_textbox.setText(str(config['hue-color-start']))
      if 'hue-flash-count' in config:
        self.flash_count_spinner.setValue(config['hue-flash-count'])
      if 'hue-transition-time' in config:
        self.flash_speed_slider.setValue(config['hue-transition-time'])

  def save(self):
    config_file = open('config.yml', 'w+')
    config = yaml.load(config_file) or {}
    config['host'] = "irc.twitch.tv"
    config['port'] = 6667
    config['channel'] = str(self.channel_textbox.text())
    config['username'] = str(self.username_textbox.text())
    config['oauth'] = str(self.oauth_textbox.text())
    config['admin-user'] = str(self.admin_textbox.text())
    config['hue-bridge-ip'] = str(self.hue_ip_textbox.text())
    config['hue-bridge-group'] = str(self.hue_group_textbox.text())
    config['hue-color-start'] = int(str(self.color_start_textbox.text()))
    config['hue-color-end'] = int(str(self.color_end_textbox.text()))
    config['hue-transition-time'] = int(self.flash_speed_slider.value())
    config['hue-flash-count'] = int(self.flash_count_spinner.value())

    noalias_dumper = yaml.dumper.SafeDumper
    noalias_dumper.ignore_aliases = lambda self, data: True

    file_contents = yaml.dump(config,
                              default_flow_style=False,
                              Dumper=noalias_dumper)

    config_file.write(file_contents)

  def close(self):
    self.hide()

  def reset(self):
    pass


class HueRetryBox(QtGui.QDialog, hue_retry_box.Ui_Dialog):
  def __init__(self, parent=None):
    super(HueRetryBox, self).__init__(parent)
    self.setupUi(self)

    self.button_box.button(QtGui.QDialogButtonBox.Cancel).clicked.connect(self.close)
    self.button_box.button(QtGui.QDialogButtonBox.Retry).clicked.connect(self.retry)

  def retry(self):
    self.close()



class MainWindow(QtGui.QMainWindow, hue_bot.Ui_main_window):
  def __init__(self, parent=None):
    super(MainWindow, self).__init__(parent)
    self.setupUi(self)

    self.config_button.clicked.connect(self.open_config)
    self.start_button.clicked.connect(self.start_bot)

    self.config_gui = ConfigWindow()
    self.config_gui.hide()

    self.bot_thread = None

  def open_config(self):
    self.config_gui.show()

  def update_list(self, line):
    self.text_list.addItem(line)

  class BotThread(QtCore.QThread):

    def run(self):
      if os.path.isfile("config.yml"):
        with open("config.yml", 'r') as config_file:
          config = yaml.load(config_file) or {}
          snake_config = {k.replace('-','_'): v
                          for k, v in config.iteritems()}
          snake_config['twitch_host'] = snake_config['host']
          snake_config['twitch_port'] = snake_config['port']
          snake_config['twitch_oauth'] = snake_config['oauth']
          snake_config['twitch_username'] = snake_config['username']
          snake_config['twitch_channel'] = snake_config['channel']
          snake_config['hue_transition_time']*=10
          bot = TwitchIrc(snake_config)

          try:
            bot.run()
          except phue.PhueRegistrationException as e:
            logger.error("Failed to register with the Hue Bridge. Push the button on the bridge.")
          except Exception as e:
            logger.error("Failed to start bot.")
            raise e

  def test_hue_connection(self, config):
    def cancel():
      raise Exception("Cancelled retry process.")

    def retry():
      self.test_hue_connection(config)

    try:
      phue.Bridge(config['hue-bridge-ip'])
    except Exception as e:
      logger.error(e.message)
      dialog = HueRetryBox()
      dialog.button_box.button(QtGui.QDialogButtonBox.Cancel).clicked.connect(cancel)
      dialog.button_box.button(QtGui.QDialogButtonBox.Retry).clicked.connect(retry)

      dialog.exec_()

  def start_bot(self):
    self.start_button.setEnabled(False)

    if os.path.isfile("config.yml"):
      with open("config.yml", 'r') as config_file:
        config = yaml.load(config_file) or {}
        self.test_hue_connection(config)
        self.bot_thread = self.BotThread()
        self.bot_thread.start()

def main():
  app = QtGui.QApplication(sys.argv)
  form = MainWindow()

  queue = Queue()
  sys.stdout = WriteStream(queue)

  # Create thread that will listen on the other end of the queue, and send the text to the textedit in our application
  thread = QtCore.QThread()
  my_receiver = MyReceiver(queue)
  my_receiver.mysignal.connect(form.update_list)
  my_receiver.moveToThread(thread)
  thread.started.connect(my_receiver.run)
  thread.start()

  form.show()

  # Only tested for Windows currently
  if sys.platform == 'win32':
    check_for_update()
  app.exec_()

def check_for_update():
  try:
    upd_log.setup_logger(level=20)

    swu_source = upd_source.UpdateGithubReleasesSource('gibsonje/hue-subscriber-bot')
    swu_updater = upd_core.Updater( current_version=package_version,
                                    update_source=swu_source)
    swu_interface = UpdatePyQt4Interface(swu_updater,
                          progname='hue-subscriber-bot',
                          ask_before_checking=False,

                          parent=QtGui.QApplication.instance())

    update_available = swu_updater.check_for_updates()

    logger.debug("Current Version: %s", swu_updater.current_version())

    if update_available:
      logger.info("Update available!")
      swu_interface.ask_to_update(update_available)
    else:
      logger.info("Already up to date!")

  except Exception as e:
    logger.error("Updater Failed")
    logger.error(e)

if __name__ == '__main__':
  main()