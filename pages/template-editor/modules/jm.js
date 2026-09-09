/**
 * JM 模块 Pages JavaScript
 * 包含 JM 配置管理的所有函数
 */

// ==================== JM 配置管理 ====================

function renderJmConfig(data) {
  document.getElementById('jm-enabled').checked = data.jm_enabled !== false;
  document.getElementById('jm-send-file').checked = data.jm_send_file !== false;
  document.getElementById('jm-max-file-size').value = data.jm_max_file_size ?? 10;
  document.getElementById('jm-cookies').value = data.jm_cookies || '';
  document.getElementById('jm-proxy').value = data.jm_proxy || '';
  document.getElementById('jm-timeout').value = data.jm_timeout ?? 20;
  document.getElementById('jm-retry-times').value = data.jm_retry_times ?? 3;
  document.getElementById('jm-image-threads').value = data.jm_image_threads ?? 16;
  document.getElementById('jm-photo-threads').value = data.jm_photo_threads ?? 4;
  document.getElementById('jm-max-concurrent').value = data.jm_max_concurrent ?? 1;
}

async function saveJmConfig() {
  const payload = {
    jm_enabled: document.getElementById('jm-enabled').checked,
    jm_send_file: document.getElementById('jm-send-file').checked,
    jm_max_file_size: Math.max(0, Math.min(50, parseInt(document.getElementById('jm-max-file-size').value) || 10)),
    jm_cookies: document.getElementById('jm-cookies').value.trim(),
    jm_proxy: document.getElementById('jm-proxy').value.trim(),
    jm_timeout: Math.max(5, Math.min(120, parseInt(document.getElementById('jm-timeout').value) || 20)),
    jm_retry_times: Math.max(1, Math.min(10, parseInt(document.getElementById('jm-retry-times').value) || 3)),
    jm_image_threads: Math.max(1, Math.min(32, parseInt(document.getElementById('jm-image-threads').value) || 16)),
    jm_photo_threads: Math.max(1, Math.min(16, parseInt(document.getElementById('jm-photo-threads').value) || 4)),
    jm_max_concurrent: Math.max(1, Math.min(3, parseInt(document.getElementById('jm-max-concurrent').value) || 1)),
  };
  try {
    await bridge.apiPost('jm/config', payload);
    showToast('JM 配置已保存');
  } catch (e) {
    showToast('保存失败: ' + (e.message || '未知错误'), 'error');
  }
}
