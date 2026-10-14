(function () {
  "use strict";

  async function responseJson(response) {
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.detail || `Request failed (${response.status}).`);
    return body;
  }

  async function cancel(session) {
    if (!session) return;
    await fetch(`/api/uploads/${session.session_id}`, {
      method: "DELETE",
      headers: { "X-Upload-Token": session.token },
    }).catch(() => {});
  }

  async function uploadFile(file, role, requestedChunkBytes, onProgress) {
    let session = null;
    try {
      session = await responseJson(await fetch("/api/uploads", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role, filename: file.name || `source-${role}`, size: file.size }),
      }));
      const chunkBytes = Math.min(requestedChunkBytes || session.chunk_bytes, session.chunk_bytes);
      let offset = session.offset || 0;
      while (offset < file.size) {
        const end = Math.min(offset + chunkBytes, file.size);
        const result = await responseJson(await fetch(`/api/uploads/${session.session_id}`, {
          method: "PATCH",
          headers: {
            "Content-Type": "application/octet-stream",
            "X-Upload-Token": session.token,
            "Upload-Offset": String(offset),
          },
          body: file.slice(offset, end),
        }));
        offset = result.offset;
        onProgress?.(offset / file.size);
      }
      await responseJson(await fetch(`/api/uploads/${session.session_id}/complete`, {
        method: "POST",
        headers: { "X-Upload-Token": session.token },
      }));
      return { session_id: session.session_id, token: session.token };
    } catch (error) {
      await cancel(session);
      throw error;
    }
  }

  window.ColorCheckUploads = { uploadFile, cancel, responseJson };
})();
