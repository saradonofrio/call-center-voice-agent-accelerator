class MicProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
  }

  process(inputs) {
    try {
      const input = inputs[0];
      if (input && input[0]) {
        // Copy the input Float32Array to avoid sharing the underlying memory
        const chunk = new Float32Array(input[0].length);
        chunk.set(input[0]);
        this.port.postMessage({ input: chunk });
      }
    } catch (e) {
      // Silence errors in the worklet to avoid crashing the audio thread
    }
    // Keep processor alive
    return true;
  }
}

registerProcessor('mic-processor', MicProcessor);
