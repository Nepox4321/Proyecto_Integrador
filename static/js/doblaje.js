document.addEventListener('DOMContentLoaded', () => {
  const videoFile = document.getElementById('videoFile');
  const video = document.getElementById('video');
  const emptyVideo = document.getElementById('emptyVideo');
  const videoHint = document.getElementById('videoHint');
  const playButton = document.getElementById('playButton');
  const scrubber = document.getElementById('scrubber');
  const currentTime = document.getElementById('currentTime');
  const duration = document.getElementById('duration');
  const speedButton = document.getElementById('speedButton');
  const recordButton = document.getElementById('recordButton');
  const recordLabel = document.getElementById('recordLabel');
  const recordState = document.getElementById('recordState');
  const recordClock = document.getElementById('recordClock');
  const recordIndicator = document.getElementById('recordIndicator');
  const permissionStatus = document.getElementById('permissionStatus');
  const levelFill = document.getElementById('levelFill');
  const takeList = document.getElementById('takeList');
  const takeCount = document.getElementById('takeCount');
  const exportSummary = document.getElementById('exportSummary');
  const exportButton = document.getElementById('exportButton');
  const newTakeButton = document.getElementById('newTakeButton');
  const clearTakesButton = document.getElementById('clearTakesButton');
  let mediaRecorder;
  let microphoneStream;
  let audioContext;
  let analyser;
  let meterFrame;
  let chunks = [];
  let takes = [];
  let recordingStartedAt = 0;
  let elapsedBeforePause = 0;
  let objectUrl;
  let audioObjectUrl;
  const speeds = [1, 0.75, 1.25];
  let speedIndex = 0;

  const formatTime = (seconds) => {
    const safeSeconds = Math.max(0, Number(seconds) || 0);
    return `${String(Math.floor(safeSeconds / 60)).padStart(2, '0')}:${String(Math.floor(safeSeconds % 60)).padStart(2, '0')}`;
  };
  const formatRecordTime = (milliseconds) => `${formatTime(milliseconds / 1000)}.${String(Math.floor((milliseconds % 1000) / 100)).padStart(1, '0')}`;
  const setStatus = (text) => { recordState.textContent = text; };

  videoFile.addEventListener('change', () => {
    const file = videoFile.files[0];
    if (!file) return;
    if (objectUrl) URL.revokeObjectURL(objectUrl);
    objectUrl = URL.createObjectURL(file);
    video.src = objectUrl;
    video.hidden = false;
    emptyVideo.hidden = true;
    videoHint.hidden = false;
    setStatus('Video listo. Activa el micrófono para comenzar.');
  });
  playButton.addEventListener('click', () => video.paused ? video.play() : video.pause());
  video.addEventListener('play', () => { playButton.textContent = '❚❚'; });
  video.addEventListener('pause', () => { playButton.textContent = '▶'; });
  video.addEventListener('loadedmetadata', () => { duration.textContent = formatTime(video.duration); scrubber.max = video.duration; });
  video.addEventListener('timeupdate', () => { currentTime.textContent = formatTime(video.currentTime); scrubber.value = video.currentTime; });
  scrubber.addEventListener('input', () => { video.currentTime = Number(scrubber.value); });
  speedButton.addEventListener('click', () => { speedIndex = (speedIndex + 1) % speeds.length; video.playbackRate = speeds[speedIndex]; speedButton.textContent = `${speeds[speedIndex]}×`; });

  const animateMeter = () => {
    if (!analyser) return;
    const values = new Uint8Array(analyser.frequencyBinCount);
    analyser.getByteTimeDomainData(values);
    const peak = values.reduce((max, value) => Math.max(max, Math.abs(value - 128)), 0) / 128;
    levelFill.style.width = `${Math.min(100, Math.max(3, peak * 180))}%`;
    meterFrame = requestAnimationFrame(animateMeter);
  };
  const stopMeter = () => { cancelAnimationFrame(meterFrame); levelFill.style.width = '0'; };

  const beginMicrophone = async () => {
    if (microphoneStream) return true;
    if (!navigator.mediaDevices || !window.MediaRecorder) {
      setStatus('Este navegador no permite grabar audio.');
      return false;
    }
    try {
      microphoneStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' : '';
      mediaRecorder = new MediaRecorder(microphoneStream, mimeType ? { mimeType } : undefined);
      audioContext = new AudioContext();
      analyser = audioContext.createAnalyser();
      analyser.fftSize = 256;
      audioContext.createMediaStreamSource(microphoneStream).connect(analyser);
      permissionStatus.textContent = 'Micrófono activo';
      document.querySelector('.status-dot').classList.add('active');
      mediaRecorder.ondataavailable = (event) => { if (event.data.size) chunks.push(event.data); };
      mediaRecorder.onstop = finishTake;
      return true;
    } catch (error) {
      setStatus('Necesitas permitir el micrófono para grabar.');
      return false;
    }
  };
  const finishTake = () => {
    const blob = new Blob(chunks, { type: mediaRecorder.mimeType || 'audio/webm' });
    if (blob.size < 100) return;
    const url = URL.createObjectURL(blob);
    takes.push({ blob, url, duration: elapsedBeforePause });
    chunks = [];
    renderTakes();
    setStatus('Toma guardada. Puedes repetirla o comenzar otra.');
  };
  const renderTakes = () => {
    takeCount.textContent = takes.length;
    exportSummary.textContent = `${takes.length} toma${takes.length === 1 ? '' : 's'} · ${takes.length ? 'audio listo' : 'sin audio'}`;
    exportButton.disabled = !takes.length;
    clearTakesButton.disabled = !takes.length;
    takeList.innerHTML = takes.length ? '' : '<p class="take-empty">Tus tomas aparecerán aquí.</p>';
    takes.forEach((take, index) => {
      const row = document.createElement('div');
      row.className = 'take-item';
      row.innerHTML = `<span class="take-number">TOMA ${String(index + 1).padStart(2, '0')}</span><span class="timecode">${formatTime(take.duration / 1000)}</span><audio controls src="${take.url}"></audio><button class="take-remove" type="button" title="Eliminar toma" aria-label="Eliminar toma">×</button>`;
      row.querySelector('.take-remove').addEventListener('click', () => { URL.revokeObjectURL(take.url); takes.splice(index, 1); renderTakes(); });
      takeList.appendChild(row);
    });
  };
  const resetClock = () => { recordingStartedAt = 0; elapsedBeforePause = 0; recordClock.textContent = '00:00.0'; };
  const updateClock = () => { const elapsed = elapsedBeforePause + (recordingStartedAt ? Date.now() - recordingStartedAt : 0); recordClock.textContent = formatRecordTime(elapsed); if (mediaRecorder && mediaRecorder.state === 'recording') requestAnimationFrame(updateClock); };

  recordButton.addEventListener('click', async () => {
    if (!mediaRecorder && !(await beginMicrophone())) return;
    if (mediaRecorder.state === 'inactive') {
      chunks = [];
      elapsedBeforePause = 0;
      recordingStartedAt = Date.now();
      mediaRecorder.start();
      if (video.src && video.paused) video.play();
      recordButton.classList.add('recording');
      recordLabel.textContent = 'Pausar toma';
      recordIndicator.classList.add('recording');
      setStatus('Grabando tu voz...');
      animateMeter();
      updateClock();
    } else if (mediaRecorder.state === 'recording') {
      elapsedBeforePause += Date.now() - recordingStartedAt;
      recordingStartedAt = 0;
      mediaRecorder.pause();
      video.pause();
      recordButton.classList.remove('recording');
      recordLabel.textContent = 'Continuar toma';
      recordIndicator.classList.remove('recording');
      stopMeter();
      setStatus('Toma en pausa. Continúa cuando estés listo.');
    } else if (mediaRecorder.state === 'paused') {
      recordingStartedAt = Date.now();
      mediaRecorder.resume();
      if (video.src && video.paused) video.play();
      recordButton.classList.add('recording');
      recordLabel.textContent = 'Pausar toma';
      recordIndicator.classList.add('recording');
      animateMeter();
      setStatus('Grabando tu voz...');
      updateClock();
    }
    newTakeButton.disabled = false;
  });
  newTakeButton.addEventListener('click', () => {
    if (!mediaRecorder || mediaRecorder.state === 'inactive') return;
    elapsedBeforePause += recordingStartedAt ? Date.now() - recordingStartedAt : 0;
    recordingStartedAt = 0;
    mediaRecorder.stop();
    video.pause();
    recordButton.classList.remove('recording');
    recordLabel.textContent = 'Grabar toma';
    recordIndicator.classList.remove('recording');
    stopMeter();
    resetClock();
  });
  clearTakesButton.addEventListener('click', () => { takes.forEach((take) => URL.revokeObjectURL(take.url)); takes = []; renderTakes(); });
  exportButton.addEventListener('click', () => {
    const merged = new Blob(takes.map((take) => take.blob), { type: takes[0].blob.type || 'audio/webm' });
    if (audioObjectUrl) URL.revokeObjectURL(audioObjectUrl);
    audioObjectUrl = URL.createObjectURL(merged);
    const link = document.createElement('a');
    link.href = audioObjectUrl;
    link.download = 'narracion-autonova.webm';
    link.click();
  });
});
