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

  const clearBtn = document.getElementById('clearBtn');
  let currentMediaUrl = '';

  // Toast notification (Retro Brutalist styling)
  function showToast(message, isError = true) {
    toast.textContent = message;
    toast.style.background = isError ? '#FFE4E6' : '#D1FAE5';
    toast.style.borderColor = '#111827';
    toast.style.color = '#111827';
    toast.style.display = 'block';
    setTimeout(() => {
      toast.style.display = 'none';
    }, 4500);
  }

  // Clear button logic
  if (clearBtn) {
    clearBtn.addEventListener('click', () => {
      urlInput.value = '';
      clearBtn.style.display = 'none';
      currentMediaUrl = '';
      resultCard.style.display = 'none';
      downloadStatus.style.display = 'none';
      if (typeof updateMobileQuickBar === 'function') updateMobileQuickBar();
      urlInput.focus();
    });
  }

  // Automatic Instant Fetch on Paste (Ctrl+V, Right-Click Paste, Mobile Long-press Paste)
  urlInput.addEventListener('paste', (e) => {
    let pastedText = '';
    if (e.clipboardData && e.clipboardData.getData) {
      pastedText = e.clipboardData.getData('text');
    } else if (window.clipboardData && window.clipboardData.getData) {
      pastedText = window.clipboardData.getData('Text');
    }

    if (pastedText && pastedText.trim()) {
      const cleanUrl = pastedText.trim();
      if (cleanUrl.startsWith('http://') || cleanUrl.startsWith('https://')) {
        if (clearBtn) clearBtn.style.display = 'flex';
        // Immediate auto-fetch
        setTimeout(() => {
          const finalVal = urlInput.value.trim() || cleanUrl;
          if (finalVal) fetchMediaInfo(finalVal);
        }, 30);
      }
    }
  });

  // Auto-fetch on Drag & Drop
  urlInput.addEventListener('drop', () => {
    setTimeout(() => {
      const val = urlInput.value.trim();
      if (val && (val.startsWith('http://') || val.startsWith('https://'))) {
        if (clearBtn) clearBtn.style.display = 'flex';
        fetchMediaInfo(val);
      }
    }, 50);
  });

  // Input change auto-detect (with light debounce for auto-complete/typing)
  let inputDebounceTimer = null;
  urlInput.addEventListener('input', () => {
    const val = urlInput.value.trim();
    if (clearBtn) {
      clearBtn.style.display = val ? 'flex' : 'none';
    }

    // If a full URL is detected and hasn't been fetched yet
    if (val && (val.startsWith('http://') || val.startsWith('https://')) && val.length > 14 && val !== currentMediaUrl && !isFetching) {
      clearTimeout(inputDebounceTimer);
      inputDebounceTimer = setTimeout(() => {
        if (val !== currentMediaUrl && !isFetching) {
          fetchMediaInfo(val);
        }
      }, 350);
    }
  });

  // Paste from clipboard button (Instant auto-fetch)
  if (pasteBtn) {
    pasteBtn.addEventListener('click', async () => {
      try {
        const text = await navigator.clipboard.readText();
        if (text && text.trim().startsWith('http')) {
          urlInput.value = text.trim();
          if (clearBtn) clearBtn.style.display = 'flex';
          fetchMediaInfo(text.trim());
        } else {
          showToast('No valid URL found in clipboard.');
        }
      } catch (err) {
        urlInput.focus();
        showToast('Please allow clipboard access or paste directly.');
      }
    });
  }

  // Search button
  if (searchBtn) {
    searchBtn.addEventListener('click', () => {
      const url = urlInput.value.trim();
      if (!url) {
        showToast('Please enter a video or post link!');
        urlInput.focus();
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

  let isFetching = false;

  // Fetch Media Information (Auto-Triggered on Paste)
  async function fetchMediaInfo(url) {
    if (!url || isFetching) return;
    isFetching = true;
    currentMediaUrl = url;
    resultCard.style.display = 'none';
    downloadStatus.style.display = 'none';
    shimmerCard.style.display = 'block'; // Show Shimmer everywhere (User Rule #12)
    if (searchBtn) {
      searchBtn.style.opacity = '0.7';
      searchBtn.style.pointerEvents = 'none';
    }

    try {
      const response = await fetch('/api/info', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url })
      });

      const data = await response.json();
      shimmerCard.style.display = 'none';
      isFetching = false;
      if (searchBtn) {
        searchBtn.style.opacity = '1';
        searchBtn.style.pointerEvents = 'auto';
      }

      if (!response.ok || data.status === 'error') {
        showToast(data.error || data.detail || 'Could not fetch media details.');
        return;
      }

      renderMediaResult(data);
    } catch (err) {
      shimmerCard.style.display = 'none';
      isFetching = false;
      if (searchBtn) {
        searchBtn.style.opacity = '1';
        searchBtn.style.pointerEvents = 'auto';
      }
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

  // Clean title helper
  function cleanTitle(raw) {
    if (!raw) return 'Media Video';
    let t = String(raw);
    // Remove hashtags (#reels, #viral, #bangla, #tiktok, etc.)
    t = t.replace(/#[\w\d_\u0980-\u09FF\u00C0-\u017F]+/g, '');
    // Remove view / reaction count prefix if present (e.g. 8.9M views • 234K reactions |)
    t = t.replace(/^\s*\d+(?:\.\d+)?[MKmk]?\s*views?\s*[•|·\s]*\d*(?:\.\d+)?[MKmk]?\s*(?:reactions?|likes?)?\s*[|•·-]\s*/i, '');
    // Clean up redundant separators
    t = t.replace(/\s*[|•·-]\s*[|•·-]+\s*/g, ' | ');
    // Clean whitespace and trim
    t = t.replace(/\s+/g, ' ').replace(/^[\s|•·-]+|[\s|•·-]+$/g, '');
    return t || 'Media Video';
  }

  // Render media result and quality selection pills
  function renderMediaResult(data) {
    resultCard.style.display = 'block';
    document.getElementById('mediaThumb').src = data.thumbnail || '/static/images/placeholder.jpg';
    document.getElementById('mediaTitle').textContent = cleanTitle(data.title);
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
      { id: '1080', label: '🎬 1080p Full HD', type: 'video', badge: 'FHD', size: '' },
      { id: '720', label: '🎬 720p HD', type: 'video', badge: 'HD', size: '' },
      { id: '480', label: '🎬 480p SD', type: 'video', badge: 'SD', size: '' },
      { id: '360', label: '🎬 360p Fast', type: 'video', badge: 'Fast', size: '' },
      { id: 'MP3', label: '🎵 MP3 Audio', type: 'audio', badge: 'Audio', size: '' }
    ];

    formats.forEach((fmt) => {
      const btn = document.createElement('button');
      btn.className = 'btn-format';
      
      const badgeClass = fmt.type === 'audio' ? 'audio' : (fmt.id === '360' ? 'fast' : '');
      const badgeText = fmt.badge || (fmt.type === 'audio' ? 'MP3' : 'MP4');

      // Specific MB / GB display
      let subDesc = '';
      if (fmt.type === 'album') {
        subDesc = `<span class="format-size-tag">💾 ${fmt.size || ''}</span> • ${fmt.badge === 'ZIP' ? 'ZIP Archive' : 'All Photos JPG'}`;
      } else if (fmt.type === 'image') {
        subDesc = `<span class="format-size-tag">💾 ${fmt.size || ''}</span> • HD Photo JPG`;
      } else if (fmt.size) {
        subDesc = `<span class="format-size-tag">💾 ${fmt.size}</span> • ${fmt.type === 'audio' ? '320kbps MP3' : 'Video MP4'}`;
      } else {
        subDesc = fmt.type === 'audio' ? 'High Quality Audio (320kbps)' : 'Direct Stream / Video MP4';
      }

      btn.innerHTML = `
        <div class="btn-format-header">
          <span class="format-label">${fmt.label}</span>
          <span class="format-badge ${badgeClass}">${badgeText}</span>
        </div>
        <span class="format-sub">${subDesc}</span>
      `;

      btn.addEventListener('click', () => {
        document.querySelectorAll('.btn-format').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        startDownload(fmt.id, fmt.type === 'audio', fmt.size);
      });

      formatGrid.appendChild(btn);
    });

    // Render album gallery if multi-photo post (Instagram/Facebook album)
    const albumGalleryWrap = document.getElementById('albumGalleryWrap');
    const albumGalleryGrid = document.getElementById('albumGalleryGrid');
    const albumCountBadge = document.getElementById('albumCountBadge');

    if (data.photos && data.photos.length > 0) {
      if (albumGalleryWrap) albumGalleryWrap.style.display = 'block';
      if (albumCountBadge) albumCountBadge.textContent = `${data.photos.length} Photos`;
      if (albumGalleryGrid) {
        albumGalleryGrid.innerHTML = '';
        data.photos.forEach((photoUrl, idx) => {
          const card = document.createElement('div');
          card.className = 'album-photo-card';
          card.innerHTML = `
            <img src="${photoUrl}" alt="Photo ${idx + 1}" class="album-photo-thumb" loading="lazy">
            <button class="album-photo-btn">
              <span>⬇️ Photo #${idx + 1}</span>
            </button>
          `;
          card.querySelector('.album-photo-btn').addEventListener('click', (e) => {
            e.stopPropagation();
            const safeTitle = (data.title || 'photo').replace(/[^a-zA-Z0-9_-]/g, '_').substring(0, 40);
            const photoName = `${safeTitle}_${idx + 1}.jpg`;
            const downloadUrl = `/api/download_image?url=${encodeURIComponent(photoUrl)}&filename=${encodeURIComponent(photoName)}`;
            _triggerAttachmentDownload(downloadUrl);
            showToast(`⬇️ Downloading Photo #${idx + 1}...`, false);
          });
          albumGalleryGrid.appendChild(card);
        });
      }
    } else {
      if (albumGalleryWrap) albumGalleryWrap.style.display = 'none';
    }

    resultCard.style.display = 'block';
    resultCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  // Trigger Download via /api/direct with Live Progress Tracking
  async function startDownload(quality, isAudio, expectedSize = '') {
    downloadStatus.style.display = 'block';
    const label = isAudio ? '🎵 MP3 Audio' : (quality === 'album' ? 'Photos' : (quality === 'img_zip' ? 'ZIP Album' : quality + 'p HD'));
    
    const statusMsg = document.getElementById('statusMsg') || statusLabel;
    const percentBadge = document.getElementById('progressPercentBadge');
    const progressBarFill = document.getElementById('progressBarFill');
    const speedEtaLabel = document.getElementById('speedEtaLabel');

    // Reset progress UI
    const sizeNote = expectedSize ? ` (${expectedSize})` : '';
    if (statusMsg) statusMsg.textContent = `⚡ Preparing ${label}${sizeNote}...`;
    if (percentBadge) percentBadge.textContent = '0%';
    if (progressBarFill) progressBarFill.style.width = '3%';
    if (speedEtaLabel) speedEtaLabel.textContent = 'Connecting to media source...';
    downloadStatus.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

    // Generate unique task_id for progress tracking
    const taskId = 'task_' + Date.now() + '_' + Math.random().toString(36).substr(2, 6);

    // Start progress polling timer
    let isFinished = false;
    let currentPct = 5;
    const progressTimer = setInterval(async () => {
      if (isFinished) {
        clearInterval(progressTimer);
        return;
      }

      // Smooth initial increment
      if (currentPct < 25) {
        currentPct += 2;
        if (progressBarFill) progressBarFill.style.width = `${currentPct}%`;
        if (percentBadge) percentBadge.textContent = `${currentPct}%`;
      }

      try {
        const pRes = await fetch(`/api/progress/${taskId}`);
        if (pRes.ok) {
          const pData = await pRes.json();
          if (pData && pData.percent !== undefined && pData.percent > 0) {
            const pct = Math.min(99, Math.max(currentPct, Math.round(pData.percent)));
            currentPct = pct;
            if (progressBarFill) progressBarFill.style.width = `${pct}%`;
            if (percentBadge) percentBadge.textContent = `${pct}%`;
            if (statusMsg && pData.msg) statusMsg.textContent = `⚡ ${pData.msg}`;

            // Live speed, size, and ETA
            if (speedEtaLabel) {
              const parts = [];
              if (pData.downloaded_mb && pData.total_mb) parts.push(`📥 ${pData.downloaded_mb} MB / ${pData.total_mb} MB`);
              if (pData.speed) parts.push(`⚡ ${pData.speed}`);
              if (pData.eta) parts.push(`⏱️ ETA: ${pData.eta}`);
              if (parts.length) {
                speedEtaLabel.textContent = parts.join(' • ');
              }
            }
          }
        }
      } catch (e) {
        // Silent catch for polling
      }
    }, 200);

    try {
      const response = await fetch('/api/direct', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          url: currentMediaUrl,
          quality: quality,
          is_audio: isAudio,
          task_id: taskId
        })
      });

      const data = await response.json();
      isFinished = true;
      clearInterval(progressTimer);

      if (!response.ok) {
        if (isAudio) {
          if (statusMsg) statusMsg.textContent = '🎵 Converting to MP3 on server...';
          await _legacyDownload(quality, isAudio);
          return;
        }
        showToast(data.detail || 'Could not get download link.');
        downloadStatus.style.display = 'none';
        return;
      }

      // Fill progress bar to 100%
      if (progressBarFill) progressBarFill.style.width = '100%';
      if (percentBadge) percentBadge.textContent = '100%';
      if (speedEtaLabel) speedEtaLabel.textContent = '✅ Complete';

      // ── MODE: redirect ── browser downloads directly via attachment proxy AND opens CDN streaming tab
      if (data.mode === 'redirect') {
        const isImg = ['jpg', 'jpeg', 'png', 'webp'].includes((data.ext || '').toLowerCase());
        if (isImg) {
          if (statusMsg) statusMsg.textContent = '✅ Photo ready! Starting download...';
          const downloadUrl = `/api/download_image?url=${encodeURIComponent(data.direct_url)}&filename=${encodeURIComponent(data.filename)}`;
          _triggerAttachmentDownload(downloadUrl);
        } else {
          if (statusMsg) statusMsg.textContent = '✅ Video ready! Starting download & streaming...';
          // 1. Direct file download to user's disk/Downloads folder
          const downloadUrl = `/api/download_video?url=${encodeURIComponent(data.direct_url)}&filename=${encodeURIComponent(data.filename)}`;
          _triggerAttachmentDownload(downloadUrl);

          // 2. Open high-speed CDN streaming player in new tab
          if (data.direct_url) {
            _triggerDownload(data.direct_url, data.filename);
          }
        }
        setTimeout(() => { downloadStatus.style.display = 'none'; }, 4000);
        return;
      }

      // ── MODE: download ── Full speed yt-dlp fetch or ZIP Archive with auto cleanup
      if (data.mode === 'download') {
        const sizeInfo = data.filesize_mb ? ` (${data.filesize_mb} MB)` : '';
        if (statusMsg) statusMsg.textContent = `✅ Ready${sizeInfo}! Starting download...`;
        _triggerAttachmentDownload(data.download_url);
        setTimeout(() => { downloadStatus.style.display = 'none'; }, 5000);
        return;
      }

      // ── MODE: stream ── VPS pipes bytes in real-time directly as attachment
      if (data.mode === 'stream') {
        if (statusMsg) statusMsg.textContent = '📡 Streaming media... download will start shortly.';
        _triggerAttachmentDownload(data.stream_url);
        setTimeout(() => { downloadStatus.style.display = 'none'; }, 4000);
        return;
      }

      // ── MODE: images ── download each image sequentially directly as attachments
      if (data.mode === 'images') {
        const urls = data.image_urls || [];
        if (!urls.length) {
          showToast('No images found in this post.');
          downloadStatus.style.display = 'none';
          return;
        }
        if (statusMsg) statusMsg.textContent = `🖼️ Downloading ${urls.length} photo(s)...`;
        const safeTitle = (data.title || 'photo').replace(/[^a-zA-Z0-9_-]/g, '_').substring(0, 40);

        urls.forEach((imgUrl, i) => {
          setTimeout(() => {
            const photoName = `${safeTitle}_${i + 1}.jpg`;
            const downloadUrl = `/api/download_image?url=${encodeURIComponent(imgUrl)}&filename=${encodeURIComponent(photoName)}`;
            _triggerAttachmentDownload(downloadUrl);
          }, i * 350);
        });

        setTimeout(() => {
          if (statusMsg) statusMsg.textContent = `✅ All ${urls.length} photos downloaded!`;
          setTimeout(() => { downloadStatus.style.display = 'none'; }, 3500);
        }, urls.length * 350 + 1000);
        return;
      }

      showToast('Unexpected response from server.');
      downloadStatus.style.display = 'none';

    } catch (err) {
      isFinished = true;
      clearInterval(progressTimer);
      downloadStatus.style.display = 'none';
      showToast('Error occurred while fetching download link.');
      console.error(err);
    }
  }

  // Helper: trigger direct attachment file download (direct save to disk!)
  function _triggerAttachmentDownload(url, filename) {
    const a = document.createElement('a');
    a.href = url;
    if (filename) a.download = filename;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => {
      if (document.body.contains(a)) {
        document.body.removeChild(a);
      }
    }, 1000);
  }

  // Helper: trigger a browser download via hidden <a> opening in new tab
  function _triggerDownload(url, filename) {
    const a = document.createElement('a');
    a.href = url;
    a.download = filename || 'download';
    a.target = '_blank';
    a.rel = 'noopener noreferrer';
    document.body.appendChild(a);
    a.click();
    setTimeout(() => {
      if (document.body.contains(a)) {
        document.body.removeChild(a);
      }
    }, 400);
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

    } catch (err) {
      downloadStatus.style.display = 'none';
      showToast('Error occurred while downloading.');
    }
  }

  // Floating Quick Paste Bar on Mobile (Only appears on scroll when no results are shown)
  const mobileQuickBar = document.getElementById('mobileQuickBar');
  const mobileFloatPasteBtn = document.getElementById('mobileFloatPasteBtn');

  function updateMobileQuickBar() {
    if (!mobileQuickBar) return;
    const isResultShowing = resultCard && resultCard.style.display !== 'none';
    const isDownloadShowing = downloadStatus && downloadStatus.style.display !== 'none';
    const isShimmerShowing = shimmerCard && shimmerCard.style.display !== 'none';

    // Hide immediately if results, download, or shimmer is on screen
    if (isResultShowing || isDownloadShowing || isShimmerShowing) {
      mobileQuickBar.style.opacity = '0';
      mobileQuickBar.style.pointerEvents = 'none';
      mobileQuickBar.style.transform = 'translateY(16px)';
      return;
    }

    // Only show if user scrolled down on mobile and page has no active media card
    if (window.innerWidth <= 640 && window.scrollY > 380) {
      mobileQuickBar.style.opacity = '1';
      mobileQuickBar.style.pointerEvents = 'auto';
      mobileQuickBar.style.transform = 'translateY(0)';
    } else {
      mobileQuickBar.style.opacity = '0';
      mobileQuickBar.style.pointerEvents = 'none';
      mobileQuickBar.style.transform = 'translateY(16px)';
    }
  }

  if (mobileFloatPasteBtn) {
    mobileFloatPasteBtn.addEventListener('click', async () => {
      // Scroll to downloader box smoothly
      const box = document.getElementById('downloader-box');
      if (box) {
        box.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }

      try {
        const text = await navigator.clipboard.readText();
        if (text && text.trim().startsWith('http')) {
          urlInput.value = text.trim();
          if (clearBtn) clearBtn.style.display = 'flex';
          fetchMediaInfo(text.trim());
        } else {
          urlInput.focus();
        }
      } catch (err) {
        urlInput.focus();
      }
    });

    window.addEventListener('scroll', updateMobileQuickBar);
    window.addEventListener('resize', updateMobileQuickBar);
  }

  // Dynamic ScrollSpy for Header Navigation Links
  const navItems = document.querySelectorAll('.nav-links .nav-item');
  const sections = [
    { id: 'downloader-box', navItem: document.querySelector('.nav-links a[href="#downloader-box"]') },
    { id: 'services', navItem: document.querySelector('.nav-links a[href="#services"]') },
    { id: 'how-it-works', navItem: document.querySelector('.nav-links a[href="#how-it-works"]') },
    { id: 'tech-stack', navItem: document.querySelector('.nav-links a[href="#tech-stack"]') },
    { id: 'platforms', navItem: document.querySelector('.nav-links a[href="#platforms"]') }
  ];

  function setActiveNavItem(targetItem) {
    navItems.forEach(item => item.classList.remove('active'));
    if (targetItem) targetItem.classList.add('active');
  }

  // Click on nav item directly updates active state
  navItems.forEach(item => {
    item.addEventListener('click', () => {
      setActiveNavItem(item);
    });
  });

  // ScrollSpy listener updates active link on scroll
  let scrollSpyTimer = null;
  window.addEventListener('scroll', () => {
    if (scrollSpyTimer) return;
    scrollSpyTimer = setTimeout(() => {
      scrollSpyTimer = null;
      const scrollPos = window.scrollY + 180;

      let currentActiveItem = sections[0].navItem;
      for (let i = sections.length - 1; i >= 0; i--) {
        const secElem = document.getElementById(sections[i].id);
        if (secElem) {
          const top = secElem.offsetTop;
          if (scrollPos >= top) {
            currentActiveItem = sections[i].navItem;
            break;
          }
        }
      }

      if (currentActiveItem && !currentActiveItem.classList.contains('active')) {
        setActiveNavItem(currentActiveItem);
      }
    }, 50);
  });
});
