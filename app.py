from flask import Flask, render_template, jsonify, Response
import json
import time
import threading
import queue
from speech_recognition import Recognizer, Microphone
from google.cloud import texttospeech
from google.cloud import speech_v1 as speech
import pygame
import os
import pyaudio
import wave
import tempfile
from pydub import AudioSegment

app = Flask(__name__)

tts_client = texttospeech.TextToSpeechClient.from_service_account_json('gcp_key.json')
speech_client = speech.SpeechClient.from_service_account_json('gcp_key.json')

FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000  # Standard rate for speech recognition
CHUNK = 1024  # Smaller chunks for faster processing
MAX_RECORDING_SECONDS = 30  # Maximum total recording time as a safety limit
SILENCE_THRESHOLD = 300  # Lowered threshold for better sensitivity
SILENCE_SECONDS = 2.0  # Stop after this many seconds of silence
MAX_SILENCE_CHUNKS = int(RATE / CHUNK * SILENCE_SECONDS)

conversation_active = False
audio_queue = queue.Queue()
transcript = []
current_question_index = 0
questions = []
current_question = None
current_answer = None
current_feedback = None
is_listening = False
is_processing = False
recording_thread = None
stop_recording = threading.Event()

def format_transcript_as_text(transcript_data):
    """Convert transcript data to formatted text with question and answer labels"""
    text_content = ""
    for entry in transcript_data:
        text_content += f"Question: {entry['question']}\n"
        text_content += f"Answer: {entry['answer']}\n"
        if "feedback" in entry:
            text_content += f"Feedback: {entry['feedback']}\n"
        text_content += "\n"
    return text_content

def load_questions():
    with open('questions.json', 'r') as f:
        data = json.load(f)
        return data.get("questions", [])

def speak_text(text):
    try:
        synthesis_input = texttospeech.SynthesisInput(text=text)
        voice = texttospeech.VoiceSelectionParams(
            language_code="en-US",
            ssml_gender=texttospeech.SsmlVoiceGender.FEMALE,
            name="en-US-Chirp3-HD-Sulafat"
        )
        
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
            speaking_rate=1.0,
            pitch=0.0
        )
        
        response = tts_client.synthesize_speech(
            input=synthesis_input,
            voice=voice,
            audio_config=audio_config
        )
        
        temp_file = "temp_speech.mp3"
        with open(temp_file, "wb") as out:
            out.write(response.audio_content)
        
        pygame.mixer.init()
        pygame.mixer.music.load(temp_file)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)
        pygame.mixer.quit()
        if os.path.exists(temp_file):
            os.remove(temp_file)
            
    except Exception as e:
        print(f"Error in text-to-speech: {e}")
        print(f"TTS failed, text was: {text}")

def convert_to_mono(input_file, output_file):
    audio = AudioSegment.from_file(input_file)
    audio = audio.set_channels(1)
    audio.export(output_file, format="wav")
    print('Converted to mono')

def record_audio():
    p = pyaudio.PyAudio()
    stream = p.open(format=FORMAT,
                   channels=CHANNELS,
                   rate=RATE,
                   input=True,
                   frames_per_buffer=CHUNK)
    
    frames = []
    silent_chunks = 0
    started = False
    max_audio_level = 0
    
    print("\n=== Starting Audio Recording ===")
    print("Waiting for speech...")
    
    try:
        while not stop_recording.is_set():
            try:
                data = stream.read(CHUNK, exception_on_overflow=False)
                frames.append(data)
                
                # Calculate audio level using RMS (Root Mean Square)
                audio_data = wave.struct.unpack("%dh" % (len(data) / 2), data)
                audio_level = int(sum(abs(x) for x in audio_data) / len(audio_data))
                max_audio_level = max(max_audio_level, audio_level)
                
                if audio_level > SILENCE_THRESHOLD and not started:
                    print(f"Speech detected! Audio level: {audio_level}")
                    started = True
                    silent_chunks = 0
                elif started:
                    if audio_level <= SILENCE_THRESHOLD:
                        silent_chunks += 1
                        if silent_chunks % 10 == 0:
                            print(f"Silence detected... {silent_chunks}/{MAX_SILENCE_CHUNKS} chunks")
                    else:
                        silent_chunks = 0
                    
                    if silent_chunks >= MAX_SILENCE_CHUNKS:
                        print("Silence threshold reached, stopping recording")
                        break
            except Exception as e:
                print(f"Error reading audio data: {e}")
                break
        
        print(f"Recording stopped. Max audio level was: {max_audio_level}")
        print(f"Recorded {len(frames)} chunks of audio")
        
        if not started:
            print("No speech detected during recording")
            return None
            
        if len(frames) < 10:  # If we recorded less than 10 chunks, it's probably not valid speech
            print("Recording too short, probably not valid speech")
            return None
            
        return frames
        
    except Exception as e:
        print(f"Error in record_audio: {e}")
        return None
    finally:
        print("Cleaning up audio recording resources")
        stream.stop_stream()
        stream.close()
        p.terminate()

def save_audio_to_wav(frames, filename):
    """Save recorded audio frames to WAV file"""
    wf = wave.open(filename, 'wb')
    wf.setnchannels(CHANNELS)
    wf.setsampwidth(2)  # 2 bytes for paInt16
    wf.setframerate(RATE)
    wf.writeframes(b''.join(frames))
    wf.close()

def transcribe_audio(audio_file):
    """Transcribe audio using Google Cloud Speech-to-Text"""
    try:
        print(f"\n=== Starting Transcription ===")
        
        with open(audio_file, 'rb') as audio_file:
            content = audio_file.read()
            print(f"Read {len(content)} bytes from audio file")
        
        audio = speech.RecognitionAudio(content=content)
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=RATE,
            language_code='en-US',
            enable_automatic_punctuation=True
        )
        
        print("Sending request to Google Speech-to-Text")
        response = speech_client.recognize(config=config, audio=audio)
        
        if response.results:
            transcript_text = response.results[0].alternatives[0].transcript
            confidence = response.results[0].alternatives[0].confidence
            print(f'Transcript: {transcript_text}')
            print(f'Confidence: {confidence}')
            return transcript_text
        else:
            print("No transcription results returned")
            return None
            
    except Exception as e:
        print(f"Error in transcription: {e}")
        return None

def recognize_speech():
    """Record and transcribe speech"""
    global is_listening, current_answer
    
    print("\n=== Starting Speech Recognition ===")
    is_listening = True
    stop_recording.clear()
    
    temp_file = None
    
    try:
        # Record audio
        print("Recording audio...")
        frames = record_audio()
        
        if not frames:
            print("No audio frames recorded")
            is_listening = False
            return None
        
        print(f"Recorded {len(frames)} audio frames")
        
        # Save to temporary file
        temp_file = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
        temp_file.close()  # Close the file so it can be used by other processes
        
        print(f"Saving audio to temporary file: {temp_file.name}")
        save_audio_to_wav(frames, temp_file.name)
        
        # Transcribe the audio
        print("Transcribing audio...")
        text = transcribe_audio(temp_file.name)
        print(f"Transcription result: {text}")
        
        is_listening = False
        
        if text and text.strip():
            print(f"Transcription successful: {text}")
            current_answer = text
            return text
        else:
            print("Transcription returned empty result")
            return None
            
    except Exception as e:
        print(f"Error in recognize_speech: {e}")
        is_listening = False
        return None
    finally:
        # Clean up temporary files
        try:
            if temp_file and os.path.exists(temp_file.name):
                os.unlink(temp_file.name)
        except Exception as e:
            print(f"Error cleaning up temp file: {e}")

# Conversation thread function
def conversation_thread():
    global conversation_active, current_question_index, transcript, questions, current_question, current_answer, is_listening
    
    print(f"Starting conversation thread. Total questions: {len(questions)}")
    
    while conversation_active and current_question_index < len(questions):
        try:
            print(f"\n=== Processing Question {current_question_index + 1} ===")
            
            # Get current question
            current_question = questions[current_question_index]
            current_answer = None
            is_listening = False
            
            print(f"Speaking question: {current_question}")
            # Speak the question
            speak_text(current_question)
            
            # Small delay to let the question finish speaking
            time.sleep(0.5)
            
            # Set listening state
            is_listening = True
            print("Listening state set to True")
            
            # Wait for response
            print("Calling recognize_speech()")
            response = recognize_speech()
            print(f"Response received: {response}")
            
            # Clear listening state
            is_listening = False
            print("Listening state set to False")
            
            if response and response.strip():
                print(f"Valid response received: {response}")
                
                # Update current answer
                current_answer = response
                
                # Add to transcript
                transcript.append({
                    "question": current_question,
                    "answer": response
                })
                print("Added to transcript")
                
                # Wait a moment to let the UI update before moving to next question
                time.sleep(1)
                
                # Move to next question
                current_question_index += 1
                print(f"Moving to next question. New index: {current_question_index}")
                
                # If we've reached the end of questions, end the conversation
                if current_question_index >= len(questions):
                    print("Reached end of questions")
                    conversation_active = False
                    break
            else:
                print("No valid response received, retrying current question")
                time.sleep(0.5)
                continue
                
        except Exception as e:
            print(f"Error in conversation thread: {e}")
            is_listening = False
            time.sleep(0.5)
            continue
    
    print("Conversation thread ending")
    # Clean up state when conversation ends
    conversation_active = False
    current_question = None
    current_answer = None
    is_listening = False
    
    # Save transcript
    if transcript:
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        filename = f"transcript_{timestamp}.txt"
        print(f"Saving transcript to {filename}")
        
        with open(filename, 'w') as f:
            f.write(format_transcript_as_text(transcript))

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/get_questions', methods=['GET'])
def get_questions():
    global questions
    questions = load_questions()
    return jsonify({"questions": questions})

@app.route('/start_conversation', methods=['POST'])
def start_conversation():
    global conversation_active, current_question_index, transcript, questions, current_question, current_answer, is_listening
    
    # Reset conversation state
    conversation_active = True
    current_question_index = 0
    transcript = []
    current_question = None
    current_answer = None
    is_listening = False
    
    # Start conversation in a separate thread
    thread = threading.Thread(target=conversation_thread)
    thread.daemon = True
    thread.start()
    
    return jsonify({"success": True, "message": "Conversation started"})

@app.route('/stop_conversation', methods=['POST'])
def stop_conversation():
    global conversation_active, is_listening
    
    conversation_active = False
    is_listening = False
    
    return jsonify({"success": True, "message": "Conversation stopped"})

@app.route('/get_transcript', methods=['GET'])
def get_transcript():
    global transcript
    
    return jsonify({"transcript": transcript})

@app.route('/download_transcript', methods=['GET'])
def download_transcript():
    global transcript
    
    if not transcript:
        return "No transcript available", 404
    
    # Format transcript as text with question and answer labels
    text_content = format_transcript_as_text(transcript)
    
    # Create response with text file
    filename = f"transcript_{time.strftime('%Y%m%d-%H%M%S')}.txt"
    response = Response(text_content, mimetype='text/plain')
    response.headers.set('Content-Disposition', f'attachment; filename={filename}')
    return response

@app.route('/conversation_status', methods=['GET'])
def conversation_status():
    global conversation_active, current_question_index, questions, current_question, current_answer, is_listening
    
    status = {
        "active": conversation_active,
        "current_question_index": current_question_index,
        "total_questions": len(questions),
        "completed": current_question_index >= len(questions) if questions else False,
        "current_question": current_question,
        "current_answer": current_answer,
        "is_listening": is_listening
    }
    
    return jsonify(status)

if __name__ == '__main__':
    app.run(debug=True) 