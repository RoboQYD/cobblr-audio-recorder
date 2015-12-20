from engine import TextWriter
from engine import SystemState
from engine import Utilities
from engine import Menu
from engine import Events
import pyaudio
import wave
import time
import os
import Queue
import numpy
import fnmatch
import signal
import threading
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

signal.signal(signal.SIGINT, Utilities.GracefulExit)

class AudioState(object):
  pass

def Init():
  SystemState.AudioState = AudioState
  SystemState.AudioState.pyaudio = pyaudio.PyAudio()
  SystemState.AudioState.audio_name = None
  SystemState.AudioState.audio_file = None
  SystemState.AudioState.audio_time = 0
  SystemState.AudioState.audio_path = 'media/audio/'
  SystemState.AudioState.metadata_path = SystemState.AudioState.audio_path + '.metadata/'
  SystemState.AudioState.recording_audio = False
  SystemState.AudioState.current_audio_file = None
  SystemState.AudioState.audio_message_queue = Queue.Queue()
  SystemState.AudioState.audio_player_state = None
  MakeAudioPath()

def Process():
  button = str(SystemState.pressed_button)
  pygame = SystemState.pygame
  screen = SystemState.screen
  screen_mode = SystemState.screen_mode

  if button == 'record':
    if SystemState.AudioState.recording_audio == True:
      SystemState.AudioState.recording_audio = False
      StopRecordingAudio()
    else:
      TextWriter.Write(
          text='Rec', 
          position=(10, 10), 
          color=(255,0,0), 
          state=SystemState, 
          size=20
      )
      SystemState.AudioState.recording_audio = True
      CallRecordAudio()
  elif button == 'play':
    Menu.JumpTo(screen_mode=3, toggle=True)
    Play()
  elif button == 'pause':
    Menu.JumpTo(screen_mode=2, toggle=True)
    Pause()
  elif button == 'library':
    SystemState.AudioState.recording_audio = False
    Menu.JumpTo(screen_mode=2)
    StopRecordingAudio()
    OpenLibrary()
    Pause()
  elif button == 'go_back':
    SystemState.AudioState.recording_audio = False
    Menu.Back()
  elif button == 'rewind':
    Rewind()
  elif button == 'fast_forward':
    FastForward()
  elif button == 'next':
    if SystemState.AudioState.audio_count > 0:
      NextRecording()
  elif button == 'previous':
    if SystemState.AudioState.audio_count > 0:
      PreviousRecording()
  elif button == 'delete':
    if SystemState.AudioState.audio_count > 0:
      Menu.JumpTo(screen_mode=2)
      TextWriter.Write(
          state=SystemState, 
          text='Delete?', 
          position=(125, 75), 
          size=20
      )
  elif button == 'accept':
    DeleteAudio()
    OpenLibrary()
    Menu.Back()
  elif button == 'decline':
    OpenLibrary()
    Menu.Back()

def MakeAudioPath():
  """Makes audio path for sound recordings."""
  if os.path.exists(SystemState.AudioState.metadata_path) == False:
    os.makedirs(SystemState.AudioState.metadata_path)
  os.chown(SystemState.AudioState.metadata_path, SystemState.uid, SystemState.gid)

def CallRecordAudio():
  """Creates thread to record audio"""
  args = ()
  thread = threading.Thread(target=RecordAudio)
  thread.setDaemon(True)
  thread.start()

def RecordAudio():
  """Records single channel wave file"""
  CHUNK = 8192
  FORMAT = pyaudio.paInt16
  CHANNELS = 1
  RATE = int(SystemState.AudioState.pyaudio.get_device_info_by_index(0)['defaultSampleRate'])
  TIMESTAMP = str(int(time.time()))
  FILENAME = SystemState.AudioState.audio_path + TIMESTAMP + '.wav'
  RECORD_SECONDS = 10800
  frames = []
  audio_message_queue = None 
  SystemState.AudioState.audio_message_queue.put({'recording': True})
  
  with SystemState.AudioState.audio_message_queue.mutex:
    SystemState.AudioState.audio_message_queue.queue.clear()

  # Setting up stream.
  stream = SystemState.AudioState.pyaudio.open(
      format=FORMAT,
      channels=CHANNELS,
      rate=RATE,
      input=True,
      output=True,
      frames_per_buffer=CHUNK
  )
  

  # Recording data to a wave file.
  for i in range(0, int(RATE/CHUNK * RECORD_SECONDS)):
    data = stream.read(CHUNK)
    frames.append(data)
    
    try:
      audio_message_queue = SystemState.AudioState.audio_message_queue.get(False)
    except Queue.Empty:
      audio_message_queue = None
    
    if audio_message_queue != None:
      if audio_message_queue.get('recording') == False:
        break 


  # Stopping and closing stream.
  stream.stop_stream()
  stream.close()
  # Converting stream data into a wave file.
  wavefile = wave.open(FILENAME, 'wb')
  wavefile.setnchannels(CHANNELS)
  wavefile.setsampwidth(SystemState.AudioState.pyaudio.get_sample_size(FORMAT))
  wavefile.setframerate(RATE)
  wavefile.writeframes(b''.join(frames))
  wavefile.close()
  # Opening wave file to read and generate spectrogram.
  wavefile = wave.open(FILENAME, 'rb')
  _GenerateSpectrogram(wavefile, TIMESTAMP)
  wavefile.close()

def StopRecordingAudio():
  """Stops recording audio file."""
  SystemState.AudioState.recording_audio = False
  audio_action = {'recording': False}
  SystemState.AudioState.audio_message_queue.put(audio_action)

def OpenLibrary():
  """Open's the recording library for exploration on screen."""
  path = SystemState.AudioState.audio_path
  SystemState.AudioState.audio_archive = os.listdir(path)
  SystemState.AudioState.audio_archive = [os.path.join(path, audio) for audio in SystemState.AudioState.audio_archive]
  SystemState.AudioState.audio_archive = sorted(SystemState.AudioState.audio_archive)
  
  # Iterating through files and excluding all non-wav files.
  for name in SystemState.AudioState.audio_archive:
    if fnmatch.fnmatch(name, '*.wav') != True:
      SystemState.AudioState.audio_archive.remove(name)
  
  SystemState.AudioState.audio_count = len(SystemState.AudioState.audio_archive)

  if SystemState.AudioState.audio_count > 0:
    SystemState.AudioState.audio_index = SystemState.AudioState.audio_count - 1
    SystemState.AudioState.current_audio_file = SystemState.AudioState.audio_archive[SystemState.AudioState.audio_index]
    filename = os.path.basename(SystemState.AudioState.current_audio_file)
    filename = filename.split('.')[0]
    timestamp = filename
    filename = SystemState.AudioState.metadata_path + filename + '.png'
    timestamp = time.ctime(int(timestamp))
    ShowSpectrogram(filename)
  else:
    TextWriter.Write(
        state=SystemState, 
        text='No Recordings', 
        position=(95, 100), 
        size=20
    )

def Play():
  """Plays the selected soundbite"""
  SystemState.AudioState.audio_player_state = 'Paused'
  SystemState.AudioState.audio_name = SystemState.AudioState.audio_archive[SystemState.AudioState.audio_index]
  SystemState.pygame.mixer.music.load(SystemState.AudioState.audio_archive[SystemState.AudioState.audio_index])
  if SystemState.AudioState.audio_player_state == 'Paused' and SystemState.AudioState.audio_time > 2:
    SystemState.pygame.mixer.music.play(0, SystemState.AudioState.audio_time)
  else:
    SystemState.pygame.mixer.music.play(0, 0)

def Pause():
  """Pauses the selected soundbite"""
  SystemState.pygame.mixer.music.pause()
  SystemState.AudioState.audio_player_state = 'Paused'
  SystemState.state_history_direction = 0
  SystemState.AudioState.audio_time += SystemState.pygame.mixer.music.get_pos()/1000.0

def BlitImage(filename, pygame, screen):
  """Stamps an image on the screen"""
  try:
    raw_image = pygame.image.load(filename)
    scaled_image = pygame.transform.scale(raw_image, (320, 240))
    scaled_x = (320 - scaled_image.get_width()) / 2
    scaled_y = (240 - scaled_image.get_height()) / 2
    screen.blit(scaled_image, (scaled_x, scaled_y))
  except:
    screen.fill(0)
    TextWriter.Write(
        state=SystemState, 
        text='Spectragram Not Found', 
        position=(70, 100), 
        size=16
    )

def ShowSpectrogram(filename):
  """Shows a picture of the spectrogram on the screen"""
  pygame = SystemState.pygame
  screen = SystemState.screen
  BlitImage(filename, pygame, screen)

def FastForward():
  """Move forward in the audio file five seconds"""
  SystemState.AudioState.audio_time += 5
  SystemState.pygame.mixer.music.play(0, SystemState.AudioState.audio_time)

def Rewind():
  """Moves backward in the audio file five seconds"""
  SystemState.AudioState.audio_time -= 5
  SystemState.pygame.mixer.music.play(0, SystemState.AudioState.audio_time)
  

def DeleteAudio():
  filename = SystemState.AudioState.current_audio_file
  filename = filename.split('/')[2].split('.')[0]
  metadata_file = SystemState.AudioState.metadata_path + filename + '.png'

  """Deletes a selected soundbite and its spectrogram"""
  try:
    os.remove(SystemState.current_audio_file)
  except: # TODO:print that preview couldn't be removed.
    print "Couldn't remove preview image"

  try:
    SystemState.AudioState.audio_archive.remove(SystemState.AudioState.current_audio_file)
  except: # TODO: print that file was not removed from library.
    print "Couldn't remove from library"
 
  try:
    os.remove(metadata_file)
  except: # TODO:print that preview couldn't be removed.
    print "Couldn't remove preview image"
  

def NextRecording():
  """Changes to the next recording (Forward in the list)"""
  if SystemState.AudioState.audio_index < SystemState.AudioState.audio_count - 1:
    SystemState.AudioState.audio_index += 1
  else:
    SystemState.AudioState.audio_index = 0
  
  name = SystemState.AudioState.audio_archive[SystemState.AudioState.audio_index]
  filename = name.split('/')[2].split('.')[0]
  filename = SystemState.AudioState.metadata_path + filename + '.png'
  SystemState.AudioState.audio_name = SystemState.AudioState.audio_archive[SystemState.AudioState.audio_index]
  Play()
  ShowSpectrogram(filename)
  

def PreviousRecording():
  """Changes to the previous recording (Backwards in the list)"""
  if SystemState.AudioState.audio_index > 0:
    SystemState.AudioState.audio_index -= 1
  else:
    SystemState.AudioState.audio_index = SystemState.AudioState.audio_count - 1
  name = SystemState.AudioState.audio_archive[SystemState.AudioState.audio_index]
  filename = name.split('/')[2].split('.')[0]
  filename = SystemState.AudioState.metadata_path + filename + '.png'
  SystemState.AudioState.audio_name = SystemState.AudioState.audio_archive[SystemState.AudioState.audio_index]
  Play()
  ShowSpectrogram(filename)
  

def _GenerateSpectrogram(wavefile, timestamp):
  """Generates a spectrogram that works with the recorded sound"""
  metadata_path = SystemState.AudioState.metadata_path
  filename = metadata_path + timestamp + '.png'
  signal = wavefile.readframes(-1)
  signal = numpy.fromstring(signal, 'Int16')
  framerate = wavefile.getframerate()
  plt.title(time.ctime(float(timestamp)), fontsize=24)
  plt.subplot(111)
  plt.specgram(signal, Fs=framerate, NFFT=128, noverlap=0)
  plt.savefig(filename, dpi=100, figsize=(8,6), format='png')
  plt.close()
