/** Lazy ML worker; the normal editor remains independent of model availability. */
export function createEnhancementClient() {
  let worker, pending;
  return {
    analyze(pixels, onProgress) {
      if (pending)
        return Promise.reject(
          new Error("Enhancement analysis is already running."),
        );
      worker ??= new Worker(
        new URL("./enhancement-worker.js", import.meta.url),
        { type: "module" },
      );
      return new Promise((resolve, reject) => {
        pending = { resolve, reject };
        worker.onmessage = ({ data: m }) => {
          if (m.stage) {
            onProgress(m.stage);
            return;
          }
          const request = pending;
          pending = null;
          if (!request) return;
          m.error ? request.reject(new Error(m.error)) : request.resolve(m);
        };
        worker.onerror = () => {
          pending?.reject(
            new Error(
              "Learned enhancement is unavailable in this browser. Manual editing still works.",
            ),
          );
          pending = null;
          worker.terminate();
          worker = null;
        };
        worker.postMessage({ pixels: pixels.buffer }, [pixels.buffer]);
      });
    },
    cancel() {
      pending?.reject(new Error("Enhancement cancelled."));
      pending = null;
      worker?.terminate();
      worker = null;
    },
    async clearCache() {
      this.cancel();
      if ("caches" in globalThis)
        await caches.delete("colorcheck-enhancement-v1");
    },
  };
}
