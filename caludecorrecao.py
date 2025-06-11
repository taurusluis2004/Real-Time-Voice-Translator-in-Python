#!/usr/bin/env python3
"""
Real-time Translator for Raspberry Pi with Automatic Language Detection
Supports speech-to-text, automatic language detection, translation, and text-to-speech
Optimized for low-resource environments
"""

import speech_recognition as sr
import pyttsx3
import googletrans
from googletrans import Translator
import pyaudio
import threading
import queue
import time
import logging
from typing import Optional, Tuple
from langdetect import detect
import langdetect.lang_detect_exception

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RaspberryPiAutoTranslator:
    def __init__(self, default_target_lang='es'):
        """
        Initialize the translator with automatic language detection
        Args:
            default_target_lang: Default target language code (e.g., 'es' for Spanish)
        """
        self.default_target_lang = default_target_lang
        self.last_detected_lang = None
        
        # Initialize components
        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone()
        self.translator = Translator()
        self.tts_engine = pyttsx3.init()
        
        # Configure TTS for better performance on Pi
        self.tts_engine.setProperty('rate', 150)  # Slower speech rate
        self.tts_engine.setProperty('volume', 0.8)
        
        # Audio processing queue
        self.audio_queue = queue.Queue()
        self.is_listening = False
        self.processing_lock = threading.Lock()
        
        # Language detection confidence threshold
        self.detection_confidence = 0.8
        
        logger.info(f"Auto-translator initialized with default target: {default_target_lang}")

    def _detect_language(self, text: str) -> Optional[str]:
        """
        Detect the language of the input text
        Args:
            text: Text to analyze
        Returns:
            Detected language code or None if detection fails
        """
        try:
            # First try with langdetect library
            detected_lang = detect(text)
            logger.info(f"Language detected: {detected_lang}")
            return detected_lang
        except langdetect.lang_detect_exception.LangDetectException:
            try:
                # Fallback: try Google Translate's detection
                detection = self.translator.detect(text)
                if detection.confidence > self.detection_confidence:
                    detected_lang = detection.lang
                    logger.info(f"Language detected (Google): {detected_lang} (confidence: {detection.confidence})")
                    return detected_lang
                else:
                    logger.warning(f"Low confidence language detection: {detection.lang} ({detection.confidence})")
                    return None
            except Exception as e:
                logger.error(f"Language detection failed: {e}")
                return None
    
    def _recognize_speech(self, audio_data) -> Optional[str]:
        """
        Convert audio to text using speech recognition
        Args:
            audio_data: Audio data from microphone
        Returns:
            Recognized text or None if failed
        """
        try:
            # Use Google's speech recognition without specifying language
            text = self.recognizer.recognize_google(audio_data)
            logger.info(f"Recognized: {text}")
            return text
        except sr.UnknownValueError:
            logger.warning("Could not understand audio")
            return None
        except sr.RequestError as e:
            logger.error(f"Speech recognition error: {e}")
            return None
    
    def _determine_target_language(self, source_lang: str) -> str:
        """
        Determine target language based on source language
        Args:
            source_lang: Detected source language
        Returns:
            Target language code
        """
        # If source is the same as default target, switch to English
        if source_lang == self.default_target_lang:
            return 'en'
        else:
            return self.default_target_lang
    
    def _translate_text(self, text: str, source_lang: str, target_lang: str) -> Optional[str]:
        """
        Translate text from source to target language
        Args:
            text: Text to translate
            source_lang: Source language code
            target_lang: Target language code
        Returns:
            Translated text or None if failed
        """
        try:
            # Skip translation if source and target are the same
            if source_lang == target_lang:
                logger.info("Source and target languages are the same, skipping translation")
                return text
            
            result = self.translator.translate(text, src=source_lang, dest=target_lang)
            translated_text = result.text
            logger.info(f"Translated: {translated_text}")
            return translated_text
        except Exception as e:
            logger.error(f"Translation error: {e}")
            return None
    
    def _speak_text(self, text: str, lang: str = None):
        """
        Convert text to speech
        Args:
            text: Text to speak
            lang: Language code for TTS (optional)
        """
        try:
            logger.info(f"Speaking: {text}")
            
            # Try to set voice based on language if available
            if lang:
                voices = self.tts_engine.getProperty('voices')
                for voice in voices:
                    if lang in voice.id.lower():
                        self.tts_engine.setProperty('voice', voice.id)
                        break
            
            self.tts_engine.say(text)
            self.tts_engine.runAndWait()
        except Exception as e:
            logger.error(f"Text-to-speech error: {e}")
    
    def _get_language_name(self, lang_code: str) -> str:
        """Get human-readable language name from code"""
        return googletrans.LANGUAGES.get(lang_code, lang_code.upper())
    
    def _listen_continuously(self):
        """Continuously listen for audio input"""
        logger.info("Starting continuous listening thread")
        
        while self.is_listening:
            try:
                #print("threadlistening")
                with self.microphone as source:
                    # Listen for audio with timeout
                    logger.debug("Listening for audio...")
                    print("selfaudio")
                    audio = self.recognizer.listen(source, timeout=1, phrase_time_limit=5)
                    logger.debug("Audio captured, adding to queue")
                    self.audio_queue.put(audio)
                    
            except sr.WaitTimeoutError:
                # Normal timeout, continue listening
                logger.debug("Listen timeout - continuing")
                continue
                
            except Exception as e:
                logger.error(f"Listening error: {e}")
                time.sleep(0.1)
        
        logger.info("Listening thread stopped")
    
    def _process_audio_queue(self):
        """Process audio from the queue"""
        logger.info("Starting audio processing thread")
        
        while self.is_listening:
            print("threadprocess")
            try:
                # Wait for audio with timeout
                try:
                    audio = self.audio_queue.get(timeout=0.5)
                    logger.debug("Got audio from queue, processing...")
                except queue.Empty:
                    continue
                
                # Use lock to prevent concurrent processing
                with self.processing_lock:
                    # Recognize speech
                    text = self._recognize_speech(audio)
                    if text:
                        logger.info(f"Processing text: {text}")
                        
                        # Detect language
                        detected_lang = self._detect_language(text)
                        if detected_lang:
                            self.last_detected_lang = detected_lang
                            
                            # Determine target language
                            target_lang = self._determine_target_language(detected_lang)
                            
                            # Translate text
                            translated = self._translate_text(text, detected_lang, target_lang)
                            
                            # Print results with language information
                            source_name = self._get_language_name(detected_lang)
                            target_name = self._get_language_name(target_lang)
                            
                            print(f"\n[{source_name.upper()}] {text}")
                            if translated and detected_lang != target_lang:
                                print(f"[{target_name.upper()}] {translated}")
                                # Speak translation
                                self._speak_text(translated, target_lang)
                            else:
                                print("(No translation needed)")
                            print("-" * 50)
                        else:
                            print(f"\n[UNKNOWN LANGUAGE] {text}")
                            print("Could not detect language for translation")
                            print("-" * 50)
                    
                    # Mark task as done
                    self.audio_queue.task_done()
                
                logger.debug("Finished processing audio, continuing loop...")
                
            except Exception as e:
                logger.error(f"Audio processing error: {e}")
                # Continue the loop even if there's an error
                continue
        
        logger.info("Audio processing thread stopped")
    
    def start_translation(self):
        """Start real-time translation with auto-detection"""
        print(f"\nStarting real-time translation with automatic language detection")
        print(f"Default target language: {self._get_language_name(self.default_target_lang)}")
        print("Speak into the microphone in any language. Press Ctrl+C to stop.")
        print("Note: If you speak in the target language, it will translate to English.")
        print("-" * 50)
        
        self.is_listening = True
        
        # Start listening and processing threads
        listen_thread = threading.Thread(target=self._listen_continuously, daemon=True)
        process_thread = threading.Thread(target=self._process_audio_queue, daemon=True)
        
        listen_thread.start()
        process_thread.start()
        
        logger.info("Threads started, entering main loop")
        
        try:
            # Keep main thread alive
            while self.is_listening:
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\nStopping translator...")
            self.stop_translation()
            
            # Wait for threads to finish
            listen_thread.join(timeout=2)
            process_thread.join(timeout=2)
    
    def stop_translation(self):
        """Stop real-time translation"""
        self.is_listening = False
        logger.info("Translator stopped")
    
    def set_default_target_language(self, target_lang: str):
        """
        Change default target language
        Args:
            target_lang: New default target language code
        """
        self.default_target_lang = target_lang
        logger.info(f"Default target language changed to: {self._get_language_name(target_lang)}")
    
    def get_supported_languages(self) -> dict:
        """Get list of supported languages"""
        return googletrans.LANGUAGES
    
    def translate_text_with_detection(self, text: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Translate text with automatic language detection
        Args:
            text: Text to translate
        Returns:
            Tuple of (detected_language, target_language, translated_text)
        """
        detected_lang = self._detect_language(text)
        if detected_lang:
            target_lang = self._determine_target_language(detected_lang)
            translated = self._translate_text(text, detected_lang, target_lang)
            return detected_lang, target_lang, translated
        return None, None, None

def main():
    """Main function with interactive setup"""
    print("=== Raspberry Pi Auto-Detecting Real-time Translator ===")
    print("This translator automatically detects the language you speak!")
    print("\nPopular language codes:")
    print("en=English, es=Spanish, fr=French, de=German, it=Italian, pt=Portuguese")
    print("ja=Japanese, ko=Korean, zh=Chinese, ru=Russian, ar=Arabic, hi=Hindi")
    
    # Get default target language preference
    target = input(f"\nEnter your preferred target language code (default: es): ").strip() or 'es'
    
    # Create translator instance
    translator = RaspberryPiAutoTranslator(target)
    
    print(f"\n🎤 Ready to translate! Speaking in {translator._get_language_name(target)} will translate to English.")
    print("🎤 Speaking in other languages will translate to", translator._get_language_name(target))
    
    try:
        translator.start_translation()
    except KeyboardInterrupt:
        print("\nGoodbye!")

if __name__ == "__main__":
    main()