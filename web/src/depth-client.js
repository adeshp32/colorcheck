export function createDepthClient() {
  let worker, pending, timer;
  const cancel = (message = "Depth analysis cancelled.") => {
    clearTimeout(timer);
    worker?.terminate();
    worker = null;
    pending?.reject(new Error(message));
    pending = null;
  };
  return {
    cancel,
    async clearCache() {
      cancel();
      if ("caches" in globalThis) await caches.delete("colorcheck-depth-v1");
    },
    analyze(pixels, width, height, onProgress = () => {}) {
      if (pending)
        return Promise.reject(new Error("Depth analysis is already running."));
      worker ??= new Worker(new URL("./depth-worker.js", import.meta.url), {
        type: "module",
      });
      return new Promise((resolve, reject) => {
        pending = { resolve, reject };
        timer = setTimeout(() => {
          cancel("Depth analysis timed out. Try radial or linear blur.");
        }, 120000);
        worker.onerror = () => {
          cancel(
            "Depth analysis is unavailable in this browser. Radial and linear blur still work.",
          );
        };
        worker.onmessage = ({ data }) => {
          if (data.stage) {
            onProgress(data.stage);
            return;
          }
          clearTimeout(timer);
          pending = null;
          data.error ? reject(new Error(data.error)) : resolve(data);
        };
        worker.postMessage({ pixels: pixels.buffer, width, height }, [
          pixels.buffer,
        ]);
      });
    },
  };
}
