/**
 * Audio Worklet Processor for capturing microphone input.
 * 
 * This processor captures audio from the user's microphone and forwards it
 * to the main thread for transmission to the Voice Live API. It runs on the
 * audio rendering thread for low-latency capture.
 * 
 * Purpose:
 * - Capture Float32 PCM audio from microphone input
 * - Copy audio data to avoid memory sharing issues
 * - Send audio chunks to main thread for WebSocket transmission
 * 
 * Architecture:
 * Microphone → Web Audio API → process() → postMessage() → Main Thread → WebSocket
 * 
 * Used by: index.html's startMicrophone() function
 */
class MicProcessor extends AudioWorkletProcessor {
  /**
   * Initialize the microphone processor.
   * 
   * No special initialization needed - just calls parent constructor.
   * The actual audio capture happens in the process() method.
   */
  constructor() {
    super();
  }

  /**
   * Process microphone input (called automatically by Web Audio API).
   * 
   * This method is invoked by the browser's audio rendering thread at regular
   * intervals (typically 128 samples at a time). It captures audio from the
   * microphone and forwards it to the main thread.
   * 
   * @param {Array} inputs - Input buffers containing microphone audio data
   *                        inputs[0][0] is the first channel (mono)
   * @returns {boolean} - true to keep processor alive, false to terminate
   */
  process(inputs) {
    try {
      // ============================================================
      // CAPTURE MICROPHONE INPUT
      // ============================================================
      // Get the first input source (microphone)
      const input = inputs[0];
      
      // Verify we have valid audio data (input exists and has at least one channel)
      if (input && input[0]) {
        // ============================================================
        // COPY AUDIO DATA - Avoid memory sharing
        // ============================================================
        // Create a new Float32Array to hold the audio samples
        // IMPORTANT: We must copy the data because the input buffer is reused
        // by the Web Audio API. Sharing the underlying memory would cause
        // race conditions and corrupted audio.
        const chunk = new Float32Array(input[0].length);
        chunk.set(input[0]);
        
        // ============================================================
        // SEND TO MAIN THREAD
        // ============================================================
        // Post the audio chunk to the main thread
        // The main thread will convert Float32 → Int16 → Base64 for WebSocket
        this.port.postMessage({ input: chunk });
      }
    } catch (e) {
      // ============================================================
      // ERROR HANDLING
      // ============================================================
      // Silence errors in the worklet to avoid crashing the audio thread
      // Audio worklets run in a separate thread - uncaught errors would
      // terminate the entire audio pipeline and stop microphone capture
      // Better to skip one audio chunk than crash the whole application
    }
    
    // ============================================================
    // KEEP PROCESSOR ALIVE
    // ============================================================
    // Return true to keep the processor running for continuous capture
    // Returning false would terminate the worklet
    return true;
  }
}

// ============================================================
// REGISTER AUDIO WORKLET PROCESSOR
// ============================================================
// Register this processor with the Web Audio API
// Name 'mic-processor' is used in index.html's startMicrophone()
registerProcessor('mic-processor', MicProcessor);
