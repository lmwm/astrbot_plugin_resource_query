/**
 * MiMo 模块 Pages JavaScript
 * 包含 MiMo 账号管理的所有函数
 */

// MiMo 模块状态
let mimoEditingIndex = -1;
let mimoLoginMethod = 'password';
let mimoOtpMode = false;
const mimoTemplateResizeObserver = new ResizeObserver(entries => {
  for (const entry of entries) {
    const preview = document.getElementById('mimo-field-template-preview');
    if (preview) {
      preview.style.height = entry.target.offsetHeight + 'px';
    }
  }
});

// ==================== MiMo 账号管理 ====================

function openAddMimoModal() {
  mimoEditingIndex = -1;
  mimoLoginMethod = 'password';
  mimoOtpMode = false;
  document.getElementById('mimo-modal-title').textContent = '添加 MiMo 账号';
  document.getElementById('mimo-field-name').value = '';
  document.getElementById('mimo-field-account').value = '';
  document.getElementById('mimo-field-password').value = '';
  document.getElementById('mimo-field-device-id').value = '';
  document.getElementById('mimo-field-ua').value = '';
  document.getElementById('mimo-field-otp').value = '';
  document.getElementById('mimo-otp-section').style.display = 'none';
  document.getElementById('mimo-field-service-token').value = '';
  document.getElementById('mimo-field-user-id').value = '';
  document.getElementById('mimo-field-passtoken').value = '';
  document.getElementById('mimo-field-passtoken-user-id').value = '';
  document.getElementById('mimo-field-template').value = defaultTemplates['mimo'] || '';
  document.getElementById('mimo-login-status').style.display = 'none';
  updateMimoLoginMethodUI();

  // 默认显示账号配置部分
  switchMimoModalSection('account');

  document.getElementById('mimo-modal').classList.add('active');

  // 启动ResizeObserver
  setTimeout(startObserveMimoTemplate, 100);
}

function editMimoAccount(globalIndex) {
  mimoEditingIndex = globalIndex;
  const acc = accounts[globalIndex];
  document.getElementById('mimo-modal-title').textContent = '编辑 MiMo 账号';
  document.getElementById('mimo-field-name').value = acc.name || '';
  document.getElementById('mimo-field-account').value = acc.account || '';
  document.getElementById('mimo-field-password').value = acc.password || '';
  document.getElementById('mimo-field-device-id').value = acc.device_id || '';
  document.getElementById('mimo-field-ua').value = acc.ua || '';
  document.getElementById('mimo-field-otp').value = '';
  document.getElementById('mimo-otp-section').style.display = 'none';
  document.getElementById('mimo-field-service-token').value = acc.serviceToken || '';
  document.getElementById('mimo-field-user-id').value = acc.userId || '';
  document.getElementById('mimo-field-passtoken').value = acc.passToken || '';
  document.getElementById('mimo-field-passtoken-user-id').value = acc.userId || '';
  document.getElementById('mimo-field-template').value = acc.template || defaultTemplates['mimo'] || '';
  document.getElementById('mimo-login-status').style.display = 'none';

  // 判断登录方式（优先级：账号密码 > PassToken > ServiceToken）
  if (acc.account && acc.password) {
    mimoLoginMethod = 'password';
  } else if (acc.passToken) {
    mimoLoginMethod = 'passtoken';
  } else if (acc.serviceToken) {
    mimoLoginMethod = 'token';
  } else {
    mimoLoginMethod = 'password';
  }
  mimoOtpMode = false;
  updateMimoLoginMethodUI();

  // 默认显示账号配置部分
  switchMimoModalSection('account');

  document.getElementById('mimo-modal').classList.add('active');

  // 启动ResizeObserver
  setTimeout(startObserveMimoTemplate, 100);
}

function closeMimoModal() {
  document.getElementById('mimo-modal').classList.remove('active');
  mimoEditingIndex = -1;
  // 断开 ResizeObserver 避免内存泄漏
  mimoTemplateResizeObserver.disconnect();
}

function switchMimoLoginMethod(method) {
  mimoLoginMethod = method;
  updateMimoLoginMethodUI();
}

function switchMimoModalSection(section) {
  document.querySelectorAll('#mimo-modal .platform-tab[data-section]').forEach(tab => {
    tab.classList.toggle('active', tab.dataset.section === section);
  });
  document.getElementById('mimo-account-section').style.display = section === 'account' ? 'block' : 'none';
  document.getElementById('mimo-template-section').style.display = section === 'template' ? 'block' : 'none';

  // 切换到模板时更新预览
  if (section === 'template') {
    updateMimoFieldVariableTags();
    updateMimoFieldTemplatePreview();
  }
}

function updateMimoLoginMethodUI() {
  // 只更新登录方式相关的标签，不影响其他标签
  document.querySelectorAll('#mimo-modal .platform-tab[data-method]').forEach(tab => {
    tab.classList.toggle('active', tab.dataset.method === mimoLoginMethod);
  });
  document.getElementById('mimo-password-section').style.display = mimoLoginMethod === 'password' ? 'block' : 'none';
  document.getElementById('mimo-token-section').style.display = mimoLoginMethod === 'token' ? 'block' : 'none';
  document.getElementById('mimo-passtoken-section').style.display = mimoLoginMethod === 'passtoken' ? 'block' : 'none';
}

function toggleMimoPassword() {
  const i = document.getElementById('mimo-field-password');
  i.type = i.type === 'password' ? 'text' : 'password';
}

function showMimoLoginStatus(msg, type) {
  const el = document.getElementById('mimo-login-status');
  el.style.display = 'block';
  el.textContent = msg;
  el.style.background = type === 'error' ? '#fef2f2' : type === 'success' ? '#f0fdf4' : '#fffbeb';
  el.style.color = type === 'error' ? '#dc2626' : type === 'success' ? '#16a34a' : '#d97706';
  el.style.border = `1px solid ${type === 'error' ? '#fecaca' : type === 'success' ? '#bbf7d0' : '#fde68a'}`;
}

// ==================== MiMo 模板预览 ====================

function updateMimoFieldVariableTags() {
  updateVariableTagsGeneric('mimo');
}

function insertMimoFieldVariable(name) {
  insertVariableGeneric('mimo', name);
}

function updateMimoFieldTemplatePreview() {
  updateTemplatePreviewGeneric('mimo', false);
}

function resetMimoFieldTemplate() {
  resetTemplateGeneric('mimo');
}

function syncMimoPreviewHeight() {
  syncPreviewHeightGeneric('mimo', true);
}

// 在模态框打开时开始观察
function startObserveMimoTemplate() {
  const textarea = document.getElementById('mimo-field-template');
  if (textarea) {
    mimoTemplateResizeObserver.observe(textarea);
    syncMimoPreviewHeight();
  }
}

// ==================== MiMo 保存和测试 ====================

async function saveMimoAccount() {
  const saveBtn = document.getElementById('mimo-save-btn');
  saveBtn.disabled = true;
  saveBtn.textContent = '保存中...';

  try {
    let name = document.getElementById('mimo-field-name').value.trim();
    if (!name) {
      name = generateDefaultName('mimo');
    }

    // 收集所有字段
    const account = document.getElementById('mimo-field-account').value.trim();
    const password = document.getElementById('mimo-field-password').value.trim();
    const serviceToken = document.getElementById('mimo-field-service-token').value.trim();
    const serviceTokenUserId = document.getElementById('mimo-field-user-id').value.trim();
    const passToken = document.getElementById('mimo-field-passtoken').value.trim();
    const passTokenUserId = document.getElementById('mimo-field-passtoken-user-id').value.trim();
    const template = document.getElementById('mimo-field-template').value.trim() || defaultTemplates['mimo'] || '';

    // 检查是否有任何一种完整的凭据
    const hasPassword = account && password;
    const hasPassToken = passToken && passTokenUserId;
    const hasServiceToken = serviceToken && serviceTokenUserId;

    if (!hasPassword && !hasPassToken && !hasServiceToken) {
      showMimoLoginStatus('请至少填写一种完整的凭据：账号密码、PassToken+User ID、或 ServiceToken+User ID', 'error');
      return;
    }

    // 构建账号对象，保存所有填写的字段
    const acc = {
      platform: 'mimo',
      name: name,
      account: account || '',
      password: password || '',
      device_id: document.getElementById('mimo-field-device-id').value || '',
      ua: document.getElementById('mimo-field-ua').value || '',
      template: template
    };

    // 保存所有填写的凭据
    if (serviceToken) acc.serviceToken = serviceToken;
    if (serviceTokenUserId) acc.userId = serviceTokenUserId;
    if (passToken) acc.passToken = passToken;
    if (passTokenUserId && !acc.userId) acc.userId = passTokenUserId;

    if (mimoEditingIndex >= 0) {
      accounts[mimoEditingIndex] = acc;
    } else {
      accounts.push(acc);
    }

    await saveAccounts();
    closeMimoModal();
    showToast(mimoEditingIndex >= 0 ? 'MiMo 账号已更新' : 'MiMo 账号已添加');
  } catch (e) {
    showMimoLoginStatus('保存失败: ' + (e.message || '未知错误'), 'error');
  } finally {
    saveBtn.disabled = false;
    saveBtn.textContent = '💾 保存';
  }
}

async function testMimoAccount() {
  const testBtn = document.getElementById('mimo-test-btn');
  testBtn.disabled = true;
  testBtn.textContent = '测试中...';

  try {
    const account = document.getElementById('mimo-field-account').value.trim();
    const password = document.getElementById('mimo-field-password').value.trim();
    const otpCode = document.getElementById('mimo-field-otp').value.trim();
    const passToken = document.getElementById('mimo-field-passtoken').value.trim();
    const passTokenUserId = document.getElementById('mimo-field-passtoken-user-id').value.trim();
    const serviceToken = document.getElementById('mimo-field-service-token').value.trim();
    const serviceTokenUserId = document.getElementById('mimo-field-user-id').value.trim();

    // 检查是否有任何一种完整的凭据
    const hasPassword = account && password;
    const hasPassToken = passToken && passTokenUserId;
    const hasServiceToken = serviceToken && serviceTokenUserId;

    if (!hasPassword && !hasPassToken && !hasServiceToken) {
      showMimoLoginStatus('请至少填写一种完整的凭据后再测试', 'error');
      return;
    }

    // 如果有账号密码，使用登录 API（支持 OTP）
    if (hasPassword) {
      if (mimoOtpMode && !otpCode) {
        showMimoLoginStatus('请输入验证码', 'error');
        return;
      }

      showMimoLoginStatus(mimoOtpMode ? '正在验证...' : '正在登录...', 'info');

      // 先保存账号（如果还没有保存）
      let name = document.getElementById('mimo-field-name').value.trim();
      if (!name) {
        name = generateDefaultName('mimo');
      }

      const acc = {
        platform: 'mimo',
        name: name,
        account: account,
        password: password,
        device_id: document.getElementById('mimo-field-device-id').value || '',
        ua: document.getElementById('mimo-field-ua').value || ''
      };

      // 如果是编辑模式，保留原有的凭据
      if (mimoEditingIndex >= 0) {
        const oldAcc = accounts[mimoEditingIndex];
        acc.userId = oldAcc.userId || '';
        acc.passToken = oldAcc.passToken || '';
        acc.serviceToken = oldAcc.serviceToken || '';
      }

      if (mimoEditingIndex >= 0) {
        accounts[mimoEditingIndex] = acc;
      } else {
        accounts.push(acc);
      }
      await saveAccounts();

      // 重新获取mimo账号列表和索引
      const mimoAccounts = accounts.filter(a => a.platform === 'mimo');
      let mimoIdx = -1;
      for (let i = 0; i < mimoAccounts.length; i++) {
        if (mimoAccounts[i].name === name && mimoAccounts[i].account === account) {
          mimoIdx = i;
          break;
        }
      }

      if (mimoIdx < 0) {
        mimoIdx = mimoAccounts.length - 1;
      }

      // 调用登录API
      const postData = {
        index: mimoIdx,
        account: account,
        password: password
      };
      if (mimoOtpMode && otpCode) {
        postData.otp_code = otpCode;
      }

      const result = await bridge.apiPost('mimo/login', postData);

      if (result && result.status === 'ok') {
        showMimoLoginStatus('✅ 测试成功', 'success');
        mimoOtpMode = false;
        document.getElementById('mimo-otp-section').style.display = 'none';

        // 更新账号信息并保存到配置
        if (result.account) {
          const idx = accounts.findIndex(a => a.platform === 'mimo' && a.name === name && a.account === account);
          if (idx >= 0) {
            accounts[idx] = { ...accounts[idx], ...result.account };
          }
          // 自动填写获取到的凭证
          if (result.account.userId) {
            document.getElementById('mimo-field-user-id').value = result.account.userId;
            document.getElementById('mimo-field-passtoken-user-id').value = result.account.userId;
          }
          if (result.account.passToken) {
            document.getElementById('mimo-field-passtoken').value = result.account.passToken;
          }
          if (result.account.serviceToken) {
            document.getElementById('mimo-field-service-token').value = result.account.serviceToken;
          }
          // 自动保存凭据到配置
          await saveAccounts();
        }
        renderAccounts();
      } else if (result && result.status === 'otp_required') {
        mimoOtpMode = true;
        document.getElementById('mimo-otp-section').style.display = 'block';
        document.getElementById('mimo-field-otp').focus();
        showMimoLoginStatus('验证码已发送到您的手机，请输入6位数字验证码后再次点击测试', 'info');
      } else {
        showMimoLoginStatus(result?.message || '操作失败', 'error');
      }
      return;
    }

    // 其他凭据（PassToken、ServiceToken）使用测试 API
    showMimoLoginStatus('正在测试...', 'info');

    const testAcc = {
      platform: 'mimo',
      device_id: document.getElementById('mimo-field-device-id').value || 'wb_MIQUERY000001',
      ua: document.getElementById('mimo-field-ua').value || 'APP/com.xiaomi.mihome APPV/11.3.203 iosPassportSDK/4.2.50 iOS/26.3.1'
    };

    if (serviceToken) testAcc.serviceToken = serviceToken;
    if (serviceTokenUserId) testAcc.userId = serviceTokenUserId;
    if (passToken) testAcc.passToken = passToken;
    if (passTokenUserId && !testAcc.userId) testAcc.userId = passTokenUserId;

    const result = await bridge.apiPost('mimo/test', testAcc);

    if (result && (result.status === 'ok' || result.message === '测试成功')) {
      showMimoLoginStatus('✅ 测试成功', 'success');

      // 自动填写凭证
      const creds = result.credentials || {};
      if (creds.userId) {
        document.getElementById('mimo-field-user-id').value = creds.userId;
        document.getElementById('mimo-field-passtoken-user-id').value = creds.userId;
      }
      if (creds.passToken) {
        document.getElementById('mimo-field-passtoken').value = creds.passToken;
      }
      if (creds.serviceToken) {
        document.getElementById('mimo-field-service-token').value = creds.serviceToken;
      }

      // 自动保存凭据到配置（如果有编辑中的账号）
      if (mimoEditingIndex >= 0 && accounts[mimoEditingIndex]) {
        if (creds.userId) accounts[mimoEditingIndex].userId = creds.userId;
        if (creds.passToken) accounts[mimoEditingIndex].passToken = creds.passToken;
        if (creds.serviceToken) accounts[mimoEditingIndex].serviceToken = creds.serviceToken;
        await saveAccounts();
      }
    } else {
      const errMsg = result?.message || result?.error || '操作失败';
      showMimoLoginStatus(errMsg, 'error');
    }
  } catch (e) {
    console.error('[测试错误]', e);
    const errMsg = e.message || e.toString() || '未知错误';
    showMimoLoginStatus(errMsg, 'error');
  } finally {
    testBtn.disabled = false;
    testBtn.textContent = '🧪 测试';
  }
}

// ==================== MiMo 变量配置 ====================

function renderMimoVarList() {
  const platformData = templateVars['mimo'] || { variables: [] };
  const vars = platformData.variables || [];
  const list = document.getElementById('mimo-var-list');

  list.innerHTML = `
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
      <div style="font-size:13px;font-weight:600;color:var(--text-secondary)">变量列表</div>
      <button class="btn btn-primary btn-xs" onclick="openAddVarModal('mimo')">＋ 添加变量</button>
    </div>
    ${vars.length > 0 ? `
      <table class="var-table" style="width:100%">
        <thead>
          <tr>
            <th style="width:40px">显示</th>
            <th style="width:120px">变量名</th>
            <th>中文描述</th>
            <th style="width:150px">默认值</th>
            <th style="width:60px">操作</th>
          </tr>
        </thead>
        <tbody>
          ${vars.map((v, i) => `
            <tr>
              <td><input type="checkbox" ${v.show !== false ? 'checked' : ''} onchange="updateVarField('mimo', ${i}, 'show', this.checked)"></td>
              <td><span class="var-name">{${v.name}}</span></td>
              <td><input type="text" value="${v.desc || ''}" placeholder="中文描述" onchange="updateVarField('mimo', ${i}, 'desc', this.value)" style="width:100%"></td>
              <td><input type="text" value="${v.default || ''}" placeholder="默认值" onchange="updateVarField('mimo', ${i}, 'default', this.value)" style="width:100%"></td>
              <td><button class="btn btn-danger btn-xs" onclick="removeVariable('mimo', ${i})">删除</button></td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    ` : `
      <div class="var-empty">暂无变量，点击上方按钮添加</div>
    `}
  `;
}

async function saveMimoVarConfig() {
  try {
    await bridge.apiPost('template-vars', templateVars);
    showToast('MiMo 变量配置已保存');
  } catch (e) {
    showToast('保存失败: ' + (e.message || '未知错误'), 'error');
  }
}

// ==================== MiMo 账号渲染 ====================

function renderMimoAccounts(mimoAccounts) {
  const list = document.getElementById('mimo-account-list');
  if (!mimoAccounts || mimoAccounts.length === 0) {
    list.innerHTML = '<div class="empty-state"><div class="empty-icon">🤖</div><div class="empty-title">暂无 MiMo 账号</div><div class="empty-text">点击上方按钮添加 MiMo 账号</div></div>';
    return;
  }
  list.innerHTML = mimoAccounts.map((acc, i) => {
    const globalIndex = accounts.indexOf(acc);
    // 判断凭据类型
    let credentialType = '未配置';
    if (acc.serviceToken) {
      credentialType = 'ServiceToken';
    } else if (acc.passToken) {
      credentialType = 'PassToken';
    } else if (acc.account && acc.password) {
      credentialType = '账号密码';
    }
    return `
    <div class="account-card" onclick="editMimoAccount(${globalIndex})" style="cursor: pointer;">
      <div class="account-card-header">
        <div class="account-avatar avatar-mimo">🤖</div>
        <div class="account-info">
          <div class="account-name">${acc.name || acc.account || 'MiMo账号'}</div>
          <span class="account-platform platform-mimo">MiMo</span>
        </div>
      </div>
      <div class="account-stats">
        <div><div class="stat-label">账号</div><div class="stat-value">${acc.account || '-'}</div></div>
        <div><div class="stat-label">凭据</div><div class="stat-value">${credentialType}</div></div>
      </div>
      <div class="account-actions">
        <button class="btn btn-secondary btn-sm" onclick="event.stopPropagation(); editMimoAccount(${globalIndex})">✏️ 编辑</button>
        <button class="btn btn-danger btn-sm" onclick="event.stopPropagation(); deleteAccount(${globalIndex})">🗑️ 删除</button>
      </div>
    </div>
  `}).join('');
}
