/** Lazy client for ColorCheck's reference-conditioned V11 research model. */
export function createV11ReferenceClient() {
  let worker, pending;
  return {
    analyze(sourcePixels, referencePixels, onProgress) {
      if (pending)
        return Promise.reject(new Error("V11 analysis is already running."));
      worker ??= new Worker(
        new URL("./v11-reference-worker.js", import.meta.url),
        { type: "module" },
      );
      return new Promise((resolve, reject) => {
        pending = { resolve, reject };
        worker.onmessage = ({ data: message }) => {
          if (message.stage) {
            onProgress(message.stage);
            return;
          }
          const request = pending;
          pending = null;
          if (!request) return;
          message.error
            ? request.reject(new Error(message.error))
            : request.resolve(message);
        };
        worker.onerror = () => {
          pending?.reject(
            new Error("ColorCheck V11 is unavailable in this browser."),
          );
          pending = null;
          worker.terminate();
          worker = null;
        };
        worker.postMessage(
          {
            sourcePixels: sourcePixels.buffer,
            referencePixels: referencePixels.buffer,
          },
          [sourcePixels.buffer, referencePixels.buffer],
        );
      });
    },
    cancel() {
      pending?.reject(new Error("V11 analysis cancelled."));
      pending = null;
      worker?.terminate();
      worker = null;
    },
    async clearCache() {
      this.cancel();
      if ("caches" in globalThis)
        await caches.delete("colorcheck-v11-reference-research");
    },
  };
}
