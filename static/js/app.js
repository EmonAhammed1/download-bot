/**
 * Universal Media Downloader - Client Logic
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
          showToast('ক্লিপবোর্ডে কোনো সঠিক লিঙ্ক পাওয়া যায়নি।');
        }
      } catch (err) {
        urlInput.focus();
        showToast('ব্রাউজারের পেস্ট পারমিশন দিন বা লিঙ্কটি টাইপ করুন।');
      }
    });
  }

  // Search button
  if (searchBtn) {
    searchBtn.addEventListener('click', () => {
      const url = urlInput.value.trim();
      if (!url) {
        showToast('দয়া করে একটি লিঙ্ক পেস্ট করুন!');
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
        showToast(data.error || data.detail || 'লিঙ্কটি থেকে তথ্য আনা সম্ভব হয়নি।');
        return;
      }

      renderMediaResult(data);
    } catch (err) {
      shimmerCard.style.display = 'none';
      showToast('সার্ভারের সাথে যোগাযোগ করতে ব্যর্থ হয়েছে।');
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
        <span class="format-sub">${fmt.type === 'audio' ? 'High Quality Audio' : 'Direct Stream / Video MP4'}</span>
      `;

      btn.addEventListener('click', () => {
        startDownload(fmt.id, fmt.type === 'audio');
      });

      formatGrid.appendChild(btn);
    });

    resultCard.style.display = 'block';
    resultCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  // Trigger Download via API
  async function startDownload(quality, isAudio) {
    downloadStatus.style.display = 'block';
    statusLabel.textContent = isAudio
      ? '⚡ অডিও প্রসেস ও কনভার্ট করা হচ্ছে...'
      : `⚡ ভিডিও (${quality}p) ডাউনলোড ও প্রস্তুত করা হচ্ছে...`;
    
    downloadStatus.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

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
        showToast(resData.detail || 'ডাউনলোডে সমস্যা হয়েছে।');
        downloadStatus.style.display = 'none';
        return;
      }

      statusLabel.textContent = `✅ ডাউনলোড প্রস্তুত! (${resData.filesize_mb || '0'} MB) ব্রাউজারে নামছে...`;

      // Trigger standard browser download
      const downloadLink = document.createElement('a');
      downloadLink.href = resData.download_url;
      downloadLink.download = resData.filename;
      document.body.appendChild(downloadLink);
      downloadLink.click();
      document.body.removeChild(downloadLink);

      setTimeout(() => {
        downloadStatus.style.display = 'none';
      }, 5000);

    } catch (err) {
      downloadStatus.style.display = 'none';
      showToast('ডাউনলোড প্রক্রিয়ায় ত্রুটি হয়েছে।');
    }
  }
});
