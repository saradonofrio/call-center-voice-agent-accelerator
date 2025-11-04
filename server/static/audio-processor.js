/**
 * Audio Worklet Processor for playing AI-generated audio responses.
 * 
 * This processor implements a ring buffer to handle incoming PCM audio data
 * and stream it to the browser's audio output. It runs on the audio rendering
 * thread for low-latency playback.
 * 
 * Purpose:
 * - Receive Float32 PCM audio chunks from the main thread
 * - Buffer audio data to handle timing mismatches
 * - Stream buffered audio to the Web Audio API output
 * 
 * Architecture:
 * Main Thread → postMessage(PCM data) → AudioWorklet Thread → process() → Audio Output
 * 
 * Used by: index.html's playAudio() function
 */
class RingBufferProcessor extends AudioWorkletProcessor {
  /**
   * Initialize the ring buffer processor.
   * 
   * Sets up:
   * - Empty audio buffer to store incoming PCM data
   * - Message handler to receive audio chunks from main thread
   */
  constructor() {
    super();
    
    // Initialize empty buffer for storing incoming audio data
    // Buffer grows as new audio chunks arrive and shrinks as audio is played
    this.buffer = new Float32Array(0);
    
    // ============================================================
    // MESSAGE HANDLER - Receives audio data from main thread
    // ============================================================
    // Listen for messages from the main thread containing audio data
    this.port.onmessage = e => {
      // Handle incoming PCM audio data
      if (e.data.pcm) {
        // Create new buffer with enough space for existing + new audio
        const next = new Float32Array(this.buffer.length + e.data.pcm.length);
        
        // Copy existing buffered audio to the beginning
        next.set(this.buffer);
        
        // Append new audio data after existing buffer
        next.set(e.data.pcm, this.buffer.length);
        
        // Replace buffer with expanded version containing all audio
        this.buffer = next;
      } 
      // Handle buffer clear command (e.g., when stopping playback)
      else if (e.data.clear) {
        // Reset buffer to empty state
        this.buffer = new Float32Array(0);
      }
    };
  }

  /**
   * Process audio output (called automatically by Web Audio API).
   * 
   * This method is invoked by the browser's audio rendering thread at regular
   * intervals (typically 128 samples at a time). It fills the output buffer
   * with audio data from the ring buffer.
   * 
   * @param {Array} _ - Input buffers (unused, this is an output-only processor)
   * @param {Array} outputs - Output buffers to fill with audio data
   *                         outputs[0][0] is the first channel (mono)
   * @returns {boolean} - true to keep processor alive, false to terminate
   */
  process(_, outputs) {
    // Get the output buffer for the first channel (mono audio)
    const out = outputs[0][0];
    
    // ============================================================
    // BUFFER HAS ENOUGH DATA - Stream audio to output
    // ============================================================
    if (this.buffer.length >= out.length) {
      // Copy audio samples from buffer to output
      // Take exactly the number of samples needed for this render quantum
      out.set(this.buffer.subarray(0, out.length));
      
      // Remove the played samples from the buffer
      // Keep remaining unplayed audio for next process() call
      this.buffer = this.buffer.subarray(out.length);
    } 
    // ============================================================
    // BUFFER UNDERRUN - Not enough data available
    // ============================================================
    else {
      // Fill output with silence (zeros) to prevent audio glitches
      out.fill(0);
      
      // Clear the buffer since partial data would cause audio artifacts
      this.buffer = new Float32Array(0);
    }
    
    // Return true to keep the processor alive for continuous playback
    return true;
  }
}

// ============================================================
// REGISTER AUDIO WORKLET PROCESSOR
// ============================================================
// Register this processor with the Web Audio API
// Name 'audio-processor' is used in index.html's loadAudioProcessor()
registerProcessor('audio-processor', RingBufferProcessor);
