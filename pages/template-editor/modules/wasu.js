/**
 * 华数模块 Pages JavaScript
 * 包含华数账号管理的所有函数
 */

// 华数模块状态
let wasuEditingIndex = -1;

// ==================== 华数账号管理 ====================

function switchWasuModalSection(section) {
  document.querySelectorAll('#wasu-modal .platform-tab[data-section]').forEach(tab => {
    tab.classList.toggle('active', tab.dataset.section === section);
  });
  document.getElementById('wasu-account-section').style.display = section === 'account' ? 'block' : 'none';
  document.getElementById('wasu-template-section').style.display = section === 'template' ? 'block' : 'none';

  // 切换到模板时更新预览
  if (section === 'template') {
    updateWasuVariableTags();
    updateWasuTemplatePreview();
  }
}

function openAddWasuModal() {
  wasuEditingIndex = -1;
  document.getElementById('wasu-modal-title').textContent = '添加华数账号';
  document.getElementById('wasu-field-name').value = '';
  document.getElementById('wasu-field-phone').value = '';
  document.getElementById('wasu-field-user-key').value = '';
  document.getElementById('wasu-field-token').value = '';
  document.getElementById('wasu-field-sign').value = '';
  document.getElementById('wasu-field-template').value = defaultTemplates['wasu'] || '';

  // 默认显示账号配置部分
  switchWasuModalSection('account');

  document.getElementById('wasu-modal').classList.add('active');
}

function editWasuAccount(globalIndex) {
  wasuEditingIndex = globalIndex;
  const acc = accounts[globalIndex];
  document.getElementById('wasu-modal-title').textContent = '编辑华数账号';
  document.getElementById('wasu-field-name').value = acc.name || '';
  document.getElementById('wasu-field-phone').value = acc.phone || '';
  document.getElementById('wasu-field-user-key').value = acc.user_key || '';
  document.getElementById('wasu-field-token').value = acc.token || '';
  document.getElementById('wasu-field-sign').value = acc.sign || '';
  document.getElementById('wasu-field-template').value = acc.template || defaultTemplates['wasu'] || '';

  // 默认显示账号配置部分
  switchWasuModalSection('account');

  document.getElementById('wasu-modal').classList.add('active');
}

function closeWasuModal() {
  document.getElementById('wasu-modal').classList.remove('active');
  wasuEditingIndex = -1;
}

async function saveWasuAccount() {
  let template = document.getElementById('wasu-field-template').value.trim();
  if (!template) {
    template = defaultTemplates['wasu'] || '';
  }

  let name = document.getElementById('wasu-field-name').value.trim();
  if (!name) {
    name = generateDefaultName('wasu');
  }

  const phone = document.getElementById('wasu-field-phone').value.trim();
  const userKey = document.getElementById('wasu-field-user-key').value.trim();
  const token = document.getElementById('wasu-field-token').value.trim();

  if (!phone) {
    showToast('请输入手机号', 'error');
    return;
  }
  if (!userKey) {
    showToast('请输入 User Key', 'error');
    return;
  }
  if (!token) {
    showToast('请输入 Token', 'error');
    return;
  }

  const acc = {
    platform: 'wasu',
    name: name,
    phone: phone,
    user_key: userKey,
    token: token,
    sign: document.getElementById('wasu-field-sign').value || '',
    template: template
  };

  if (wasuEditingIndex >= 0) {
    accounts[wasuEditingIndex] = acc;
  } else {
    accounts.push(acc);
  }

  await saveAccounts();
  closeWasuModal();
  showToast(wasuEditingIndex >= 0 ? '华数账号已更新' : '华数账号已添加');
}

// ==================== 华数模板预览 ====================

function updateWasuVariableTags() {
  updateVariableTagsGeneric('wasu');
}

function insertWasuVariable(name) {
  insertVariableGeneric('wasu', name);
}

function updateWasuTemplatePreview() {
  updateTemplatePreviewGeneric('wasu', true);
}

function resetWasuTemplate() {
  resetTemplateGeneric('wasu');
}

function syncWasuPreviewHeight() {
  syncPreviewHeightGeneric('wasu', true);
}

// ==================== 华数变量配置 ====================

function renderWasuVarList() {
  const platformData = templateVars['wasu'] || { variables: [] };
  const vars = platformData.variables || [];
  const list = document.getElementById('wasu-var-list');

  list.innerHTML = `
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
      <div style="font-size:13px;font-weight:600;color:var(--text-secondary)">变量列表</div>
      <button class="btn btn-primary btn-xs" onclick="openAddVarModal('wasu')">＋ 添加变量</button>
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
              <td><input type="checkbox" ${v.show !== false ? 'checked' : ''} onchange="updateVarField('wasu', ${i}, 'show', this.checked)"></td>
              <td><span class="var-name">{${v.name}}</span></td>
              <td><input type="text" value="${v.desc || ''}" placeholder="中文描述" onchange="updateVarField('wasu', ${i}, 'desc', this.value)" style="width:100%"></td>
              <td><input type="text" value="${v.default || ''}" placeholder="默认值" onchange="updateVarField('wasu', ${i}, 'default', this.value)" style="width:100%"></td>
              <td><button class="btn btn-danger btn-xs" onclick="removeVariable('wasu', ${i})">删除</button></td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    ` : `
      <div class="var-empty">暂无变量，点击上方按钮添加</div>
    `}
  `;
}

async function saveWasuVarConfig() {
  try {
    await bridge.apiPost('template-vars', templateVars);
    showToast('华数变量配置已保存');
  } catch (e) {
    showToast('保存失败: ' + (e.message || '未知错误'), 'error');
  }
}

// ==================== 华数账号渲染 ====================

function renderWasuAccounts(wasuAccounts) {
  const list = document.getElementById('wasu-account-list');
  if (!wasuAccounts || wasuAccounts.length === 0) {
    list.innerHTML = '<div class="empty-state"><div class="empty-icon">📺</div><div class="empty-title">暂无华数账号</div><div class="empty-text">点击上方按钮添加华数账号</div></div>';
    return;
  }
  list.innerHTML = wasuAccounts.map((acc, i) => {
    const globalIndex = accounts.indexOf(acc);
    return `
    <div class="account-card" onclick="editWasuAccount(${globalIndex})" style="cursor: pointer;">
      <div class="account-card-header">
        <div class="account-avatar avatar-wasu">📺</div>
        <div class="account-info">
          <div class="account-name">${acc.name || acc.phone || '华数账号'}</div>
          <span class="account-platform platform-wasu">华数广电</span>
        </div>
      </div>
      <div class="account-stats">
        <div><div class="stat-label">手机号</div><div class="stat-value">${acc.phone || '-'}</div></div>
        <div><div class="stat-label">配置状态</div><div class="stat-value ${acc.user_key ? 'success' : 'warning'}">${acc.user_key ? '✓ 已配置' : '○ 未配置'}</div></div>
      </div>
      <div class="account-actions">
        <button class="btn btn-secondary btn-sm" onclick="event.stopPropagation(); editWasuAccount(${globalIndex})">✏️ 编辑</button>
        <button class="btn btn-danger btn-sm" onclick="event.stopPropagation(); deleteAccount(${globalIndex})">🗑️ 删除</button>
      </div>
    </div>
  `}).join('');
}
