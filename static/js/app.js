/**
 * Universal Media Downloader - Client Logic (English)
 */

document.addEventListener('DOMContentLoaded', () => {
  const urlInput = document.getElementById('urlInput');
  const pasteBtn = document.getElementById('pasteBtn');
  const searchBtn = document.getElementById('searchBtn');
  const shimmerCard = document.getElementById('shimmerCard');
  const resultCard = document.getElementById('resultCard');
  const downloadStatus = document.getElementById('downloadStatus');
  const statusLabel = document.getElementById('statusLabel');
  const toast = document.getElementById('toast');

  let currentMediaUrl = '';

  // Toast notification
  function showToast(message, isError = true) {
    toast.textContent = message;
    toast.style.borderColor = isError ? 'rgba(239, 68, 68, 0.5)' : 'rgba(16, 185, 129, 0.5)';
    toast.style.color = isError ? '#fca5a5' : '#6ee7b7';
    toast.style.display = 'block';
    setTimeout(() => {
      toast.style.display = 'none';
    }, 4500);
  }

  // Paste from clipboard
  if (pasteBtn) {
    pasteBtn.addEventListener('click', async () => {
      try {
        const text = await navigator.clipboard.readText();
        if (text && text.trim().startsWith('http')) {
          urlInput.value = text.trim();
          fetchMediaInfo(text.trim());
        } else {
          showToast('No valid URL found in clipboard.');
        }
      } catch (err) {
        urlInput.focus();
        showToast('Please allow clipboard access or type the link.');
      }
    });
  }

  // Search button
  if (searchBtn) {
    searchBtn.addEventListener('click', () => {
      const url = urlInput.value.trim();
      if (!url) {
        showToast('Please enter a video or post link!');
        return;
      }
      fetchMediaInfo(url);
    });
  }

  // Enter key support
  urlInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      const url = urlInput.value.trim();
      if (url) fetchMediaInfo(url);
    }
  });

  // Fetch Media Information
  async function fetchMediaInfo(url) {
    currentMediaUrl = url;
    resultCard.style.display = 'none';
    downloadStatus.style.display = 'none';
    shimmerCard.style.display = 'block'; // Show Shimmer everywhere (User Rule #12)

    try {
      const response = await fetch('/api/info', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url })
      });

      const data = await response.json();
      shimmerCard.style.display = 'none';

      if (!response.ok || data.status === 'error') {
        showToast(data.error || data.detail || 'Could not fetch media details.');
        return;
      }

      renderMediaResult(data);
    } catch (err) {
      shimmerCard.style.display = 'none';
      showToast('Failed to connect to the server.');
    }
  }

  // Format Duration helper
  function formatDuration(sec) {
    if (!sec || sec <= 0) return '';
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${m}:${s < 10 ? '0' : ''}${s}`;
  }

  // Render media result and quality selection pills
  function renderMediaResult(data) {
    document.getElementById('mediaThumb').src = data.thumbnail || '/static/images/placeholder.jpg';
    document.getElementById('mediaTitle').textContent = data.title || 'Media Video';
    document.getElementById('mediaPlatform').textContent = data.platform || 'Social Media';

    const durElem = document.getElementById('mediaDuration');
    if (data.duration && data.duration > 0) {
      durElem.textContent = formatDuration(data.duration);
      durElem.style.display = 'block';
    } else {
      durElem.style.display = 'none';
    }

    // Render formats grid
    const formatGrid = document.getElementById('formatGrid');
    formatGrid.innerHTML = '';

    const formats = data.formats || [
      { id: '1080', label: '🎬 1080p Full HD', type: 'video', badge: 'FHD' },
      { id: '720', label: '🎬 720p HD', type: 'video', badge: 'HD' },
      { id: '480', label: '🎬 480p SD', type: 'video', badge: 'SD' },
      { id: 'MP3', label: '🎵 MP3 Audio', type: 'audio', badge: 'Audio' }
    ];

    formats.forEach((fmt) => {
      const btn = document.createElement('button');
      btn.className = 'btn-format';
      
      const badgeClass = fmt.type === 'audio' ? 'audio' : (fmt.id === '360' ? 'fast' : '');
      const badgeText = fmt.badge || (fmt.type === 'audio' ? 'MP3' : 'MP4');

      btn.innerHTML = `
        <div class="btn-format-header">
          <span class="format-label">${fmt.label}</span>
          <span class="format-badge ${badgeClass}">${badgeText}</span>
        </div>
        <span class="format-sub">${fmt.type === 'audio' ? 'High Quality Audio (320kbps)' : 'Direct Stream / Video MP4'}</span>
      `;

      btn.addEventListener('click', () => {
        startDownload(fmt.id, fmt.type === 'audio');
      });

      formatGrid.appendChild(btn);
    });

    resultCard.style.display = 'block';
    resultCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  // Trigger Download via /api/direct (no VPS disk storage)
  async function startDownload(quality, isAudio) {
    downloadStatus.style.display = 'block';

    if (isAudio) {
      // MP3 needs FFmpeg on VPS — fallback to old /api/download
      statusLabel.textContent = '🎵 Converting to MP3... (this may take a moment)';
      downloadStatus.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      await _legacyDownload(quality, isAudio);
      return;
    }

    statusLabel.textContent = `⚡ Fetching direct link (${quality === 'album' ? 'Photos' : quality + 'p'})...`;
    downloadStatus.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

    try {
      const response = await fetch('/api/direct', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          url: currentMediaUrl,
          quality: quality,
          is_audio: isAudio
        })
      });

      const data = await response.json();

      if (!response.ok) {
        showToast(data.detail || 'Could not get download link.');
        downloadStatus.style.display = 'none';
        return;
      }

      // ── MODE: redirect ── browser downloads directly from CDN
      if (data.mode === 'redirect') {
        statusLabel.textContent = '✅ Direct link ready! Starting download...';
        _triggerDownload(data.direct_url, data.filename);
        setTimeout(() => { downloadStatus.style.display = 'none'; }, 3000);
        return;
      }

      // ── MODE: stream ── VPS pipes bytes in real-time (no disk write)
      if (data.mode === 'stream') {
        statusLabel.textContent = '📡 Streaming from source... download will start shortly.';
        _triggerDownload(data.stream_url, data.filename);
        setTimeout(() => { downloadStatus.style.display = 'none'; }, 4000);
        return;
      }

      // ── MODE: images ── download each image via direct CDN URL
      if (data.mode === 'images') {
        const urls = data.image_urls || [];
        if (!urls.length) {
          showToast('No images found in this post.');
          downloadStatus.style.display = 'none';
          return;
        }
        statusLabel.textContent = `🖼️ Downloading ${urls.length} image(s) directly...`;
        // Trigger each image download with a small delay
        urls.forEach((imgUrl, i) => {
          setTimeout(() => {
            const ext = imgUrl.split('?')[0].split('.').pop() || 'jpg';
            _triggerDownload(imgUrl, `${data.title || 'image'}_${i + 1}.${ext}`);
          }, i * 400);
        });
        setTimeout(() => { downloadStatus.style.display = 'none'; }, urls.length * 400 + 2000);
        return;
      }

      // Unknown mode — fallback
      showToast('Unexpected response from server.');
      downloadStatus.style.display = 'none';

    } catch (err) {
      downloadStatus.style.display = 'none';
      showToast('Error occurred while fetching download link.');
      console.error(err);
    }
  }

  // Helper: trigger a browser download via hidden <a>
  function _triggerDownload(url, filename) {
    const a = document.createElement('a');
    a.href = url;
    a.download = filename || 'download';
    a.rel = 'noopener';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }

  // Legacy fallback for MP3 (requires FFmpeg on VPS)
  async function _legacyDownload(quality, isAudio) {
    try {
      const response = await fetch('/api/download', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          url: currentMediaUrl,
          quality: quality,
          is_audio: isAudio
        })
      });

      const resData = await response.json();

      if (!response.ok || resData.status !== 'ready') {
        showToast(resData.detail || 'Download failed.');
        downloadStatus.style.display = 'none';
        return;
      }

      statusLabel.textContent = `✅ MP3 ready! (${resData.filesize_mb || '?'} MB) Starting download...`;
      _triggerDownload(resData.download_url, resData.filename);

      setTimeout(() => { downloadStatus.style.display = 'none'; }, 5000);

    } catch (err) {
      downloadStatus.style.display = 'none';
      showToast('Error occurred while downloading.');
    }
  }
});
