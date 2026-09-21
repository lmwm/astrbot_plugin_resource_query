/**
 * 资源查询插件 Pages 通用外壳
 *
 * 设计原则：界面完全由后端返回的模块 schema 驱动。
 * 新增功能模块时，后端实现 ModuleBase 并声明 schema 即可，
 * 本文件无需任何改动 —— 导航、配置表单、账号管理、模板编辑器
 * 都会按模块声明的能力自动渲染。
 *
 * 安全约定：所有插入 innerHTML 的外部数据一律经过 esc() 转义；
 * 所有交互通过 data-action 事件委托绑定，不使用内联事件属性。
 */
(function () {
  'use strict';

  const bridge = window.AstrBotPluginPage;

  // ══════════════════════════════════════════
  //  状态
  // ══════════════════════════════════════════

  const state = {
    version: '',
    modules: [],
    accounts: [],
    vars: {},
    activeModule: '',
    editing: null,        // { module, filename, account }
    pendingDelete: null,  // { module, filename, name }
    toastTimer: null,
  };

  // ══════════════════════════════════════════
  //  基础工具
  // ══════════════════════════════════════════

  const $ = (id) => document.getElementById(id);

  /** HTML 转义：任何要拼进 innerHTML 的外部数据都必须先经过它 */
  function esc(value) {
    const text = value === undefined || value === null ? '' : String(value);
    return text.replace(/[&<>"']/g, (c) => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;',
    })[c]);
  }

  function toast(message, type) {
    const el = $('toast');
    if (!el) return;

    el.textContent = message;
    el.className = 'toast show' + (type === 'error' ? ' error' : '');

    if (state.toastTimer) clearTimeout(state.toastTimer);
    state.toastTimer = setTimeout(() => {
      el.className = 'toast';
    }, 3000);
  }

  /** 在账号模态框内部显示状态，避免提示落到隐藏容器里 */
  function setStatus(message, type) {
    const el = $('account-status');
    if (!el) return;

    if (!message) {
      el.style.display = 'none';
      return;
    }

    el.textContent = message;
    el.className = 'status-box ' + (type || 'ok');
    el.style.display = '';
  }

  /** 整数解析：保留 0（"0 表示不限制"这类语义不能被 || 吞掉） */
  function toInt(value, fallback) {
    const num = parseInt(value, 10);
    if (Number.isNaN(num)) return fallback === undefined ? 0 : fallback;
    return num;
  }

  // ══════════════════════════════════════════
  //  API
  // ══════════════════════════════════════════

  /** 统一请求：后端返回 error 时抛错，由调用方决定如何提示 */
  async function request(endpoint, payload, method) {
    const result = method === 'GET'
      ? await bridge.apiGet(endpoint, payload)
      : await bridge.apiPost(endpoint, payload);

    if (result && result.status === 'error') {
      throw new Error(result.message || '请求失败');
    }

    return result || {};
  }

  const api = {
    get: (endpoint, params) => request(endpoint, params, 'GET'),
    post: (endpoint, body) => request(endpoint, body, 'POST'),
  };

  // ══════════════════════════════════════════
  //  数据加载
  // ══════════════════════════════════════════

  async function loadModules() {
    const data = await api.get('modules');
    state.version = data.version || '';
    state.modules = data.modules || [];
  }

  async function loadAccounts() {
    const data = await api.get('accounts');
    state.accounts = data.accounts || [];
  }

  async function loadVars() {
    state.vars = await api.get('template-vars');
  }

  /** 加载各模块自有配置：单个模块失败只影响它自己，绝不用空值覆盖后端配置 */
  async function loadModuleConfigs() {
    await Promise.all(state.modules.map(async (mod) => {
      if (!mod.config_fields || !mod.config_fields.length) {
        mod.config = {};
        return;
      }
      try {
        mod.config = await api.get(mod.name + '/config');
      } catch (e) {
        mod.config = null; // null 表示"未取到"，渲染时回退到字段默认值
      }
    }));
  }

  /** 并行加载全部数据：任一失败只提示，不中断其余 */
  async function loadAll() {
    const problems = [];

    await Promise.all([
      loadModules().catch((e) => { problems.push('模块列表(' + e.message + ')'); }),
      loadAccounts().catch((e) => { problems.push('账号列表(' + e.message + ')'); }),
      loadVars().catch((e) => { problems.push('模板变量(' + e.message + ')'); }),
    ]);

    await loadModuleConfigs();

    if (problems.length) {
      toast('部分数据加载失败：' + problems.join('，'), 'error');
    }
  }

  // ══════════════════════════════════════════
  //  查询辅助
  // ══════════════════════════════════════════

  const moduleByName = (name) => state.modules.find((m) => m.name === name) || null;
  const accountsOf = (name) => state.accounts.filter((a) => a.platform === name);
  const variablesOf = (name) => (state.vars[name] && state.vars[name].variables) || [];

  const accountLabel = (acc, fallback) =>
    acc.name || acc.account || acc.phone || fallback || '未命名账号';

  const defaultTemplate = (name) => {
    const mod = moduleByName(name);
    return (mod && mod.default_template) || '';
  };

  // ══════════════════════════════════════════
  //  渲染：导航与页面
  // ══════════════════════════════════════════

  function renderNav() {
    const nav = $('nav-tabs');
    nav.innerHTML = '';

    state.modules.forEach((mod) => {
      const btn = document.createElement('button');
      btn.className = 'nav-tab' + (mod.name === state.activeModule ? ' active' : '');
      btn.textContent = (mod.icon ? mod.icon + ' ' : '') + mod.title;
      btn.dataset.action = 'select-module';
      btn.dataset.module = mod.name;
      nav.appendChild(btn);
    });
  }

  function renderPages() {
    const container = $('pages');
    container.innerHTML = '';

    if (!state.modules.length) {
      container.innerHTML =
        '<div class="card"><div class="card-body"><div class="empty">' +
        '没有已启用的功能模块。<br>请在 AstrBot 的插件配置中开启至少一个模块后重载插件。' +
        '</div></div></div>';
      return;
    }

    state.modules.forEach((mod) => {
      const page = document.createElement('div');
      page.className = 'page' + (mod.name === state.activeModule ? ' active' : '');
      page.id = 'page-' + mod.name;
      page.innerHTML = buildPageHtml(mod);
      container.appendChild(page);

      if (mod.supports_accounts) renderAccountList(mod);
      if (Object.keys(mod.variables || {}).length) renderVarTable(mod);
    });
  }

  /** 按模块声明的能力拼装页面骨架 */
  function buildPageHtml(mod) {
    const parts = [
      '<div class="module-head">' +
        '<h2>' + esc((mod.icon ? mod.icon + ' ' : '') + mod.title) + '</h2>' +
        (mod.desc ? '<p>' + esc(mod.desc) + '</p>' : '') +
      '</div>',
    ];

    if (mod.supports_accounts) {
      parts.push(
        '<div class="card">' +
          '<div class="card-header">' +
            '<span class="card-title">账号管理</span>' +
            '<button class="btn btn-primary btn-sm" data-action="add-account" data-module="' + esc(mod.name) + '">＋ 添加账号</button>' +
          '</div>' +
          '<div class="card-body"><div class="account-grid" id="list-' + esc(mod.name) + '"></div></div>' +
        '</div>'
      );
    }

    if ((mod.config_fields || []).length) {
      parts.push(
        '<div class="card">' +
          '<div class="card-header">' +
            '<span class="card-title">模块设置</span>' +
            '<button class="btn btn-primary btn-sm" data-action="save-config" data-module="' + esc(mod.name) + '">保存设置</button>' +
          '</div>' +
          '<div class="card-body">' + buildConfigFieldsHtml(mod) + '</div>' +
        '</div>'
      );
    }

    if (Object.keys(mod.variables || {}).length) {
      parts.push(
        '<div class="card">' +
          '<div class="card-header">' +
            '<span class="card-title">模板变量</span>' +
            '<button class="btn btn-primary btn-sm" data-action="save-vars" data-module="' + esc(mod.name) + '">保存变量</button>' +
          '</div>' +
          '<div class="card-body"><div class="table-scroll"><table class="var-table">' +
            '<thead><tr><th>变量名</th><th>说明</th><th>示例值</th><th>显示</th><th></th></tr></thead>' +
            '<tbody id="vars-' + esc(mod.name) + '"></tbody>' +
          '</table></div></div>' +
        '</div>'
      );
    }

    return parts.join('');
  }

  function buildConfigFieldsHtml(mod) {
    const config = mod.config || {};

    return (mod.config_fields || []).map((field) => {
      const raw = config[field.key];
      const value = raw === undefined ? (field.default === undefined ? '' : field.default) : raw;
      const id = 'cfg-' + mod.name + '-' + field.key;

      if (field.type === 'bool') {
        return '<div class="form-group">' +
          '<label class="switch"><input type="checkbox" id="' + esc(id) + '"' + (value ? ' checked' : '') + '>' +
          esc(field.label) + '</label>' +
          (field.hint ? '<div class="hint">' + esc(field.hint) + '</div>' : '') +
          '</div>';
      }

      const type = field.type === 'password' ? 'password' : (field.type === 'int' ? 'number' : 'text');

      return '<div class="form-group">' +
        '<label class="form-label" for="' + esc(id) + '">' + esc(field.label) + '</label>' +
        '<input class="form-input" type="' + type + '" id="' + esc(id) + '" value="' + esc(value) + '">' +
        (field.hint ? '<div class="hint">' + esc(field.hint) + '</div>' : '') +
        '</div>';
    }).join('');
  }

  function renderAccountList(mod) {
    const box = $('list-' + mod.name);
    if (!box) return;

    const list = accountsOf(mod.name);

    if (!list.length) {
      box.innerHTML = '<div class="empty">还没有账号，点击右上角「添加账号」</div>';
      return;
    }

    box.innerHTML = list.map((acc, index) => {
      const label = accountLabel(acc, '账号' + (index + 1));
      const sub = acc.account || acc.phone || '';
      const badge = acc.serviceToken
        ? '<span class="badge ok">已登录</span>'
        : (mod.supports_login ? '<span class="badge off">未登录</span>' : '');

      return '<div class="account-card">' +
        '<div class="account-main" data-action="edit-account" data-module="' + esc(mod.name) + '" data-file="' + esc(acc._filename || '') + '">' +
          '<div class="account-title">' + esc(label) + ' ' + badge + '</div>' +
          (sub ? '<div class="account-sub">' + esc(sub) + '</div>' : '') +
        '</div>' +
        '<button class="btn btn-danger btn-xs" data-action="delete-account" ' +
          'data-module="' + esc(mod.name) + '" data-file="' + esc(acc._filename || '') + '" ' +
          'data-name="' + esc(label) + '">删除</button>' +
      '</div>';
    }).join('');
  }

  function renderVarTable(mod) {
    const tbody = $('vars-' + mod.name);
    if (!tbody) return;

    const list = variablesOf(mod.name);

    if (!list.length) {
      tbody.innerHTML = '<tr><td colspan="5" class="empty">暂无变量</td></tr>';
      return;
    }

    tbody.innerHTML = list.map((item, index) => '<tr>' +
      '<td><input type="text" data-var="name" data-index="' + index + '" value="' + esc(item.name || '') + '"></td>' +
      '<td><input type="text" data-var="desc" data-index="' + index + '" value="' + esc(item.desc || '') + '"></td>' +
      '<td><input type="text" data-var="default" data-index="' + index + '" value="' + esc(item.default || '') + '"></td>' +
      '<td><input type="checkbox" data-var="show" data-index="' + index + '"' + (item.show !== false ? ' checked' : '') + '></td>' +
      '<td><button class="btn btn-danger btn-xs" data-action="remove-var" ' +
        'data-module="' + esc(mod.name) + '" data-index="' + index + '">✕</button></td>' +
    '</tr>').join('');
  }

  function selectModule(name) {
    state.activeModule = name;

    document.querySelectorAll('.nav-tab').forEach((tab) => {
      tab.classList.toggle('active', tab.dataset.module === name);
    });

    document.querySelectorAll('.page').forEach((page) => {
      page.classList.toggle('active', page.id === 'page-' + name);
    });
  }

  // ══════════════════════════════════════════
  //  账号模态框
  // ══════════════════════════════════════════

  function openAccountModal(moduleName, filename) {
    const mod = moduleByName(moduleName);
    if (!mod) return;

    const account = filename
      ? accountsOf(moduleName).find((a) => a._filename === filename)
      : null;

    state.editing = { module: mod, filename: filename || '', account: account || {} };

    $('account-modal-title').textContent = (account ? '编辑 ' : '添加 ') + mod.title + ' 账号';

    setStatus('');
    $('account-otp').value = '';
    $('account-otp-row').style.display = 'none';

    $('account-form').innerHTML = (mod.account_fields || [])
      .map((field) => buildAccountFieldHtml(mod, field))
      .join('');

    const btnLogin = $('btn-login');
    btnLogin.style.display = mod.supports_login ? '' : 'none';
    btnLogin.disabled = !account;
    btnLogin.title = account ? '' : '请先保存账号，再执行登录';

    $('btn-test').style.display = mod.supports_test ? '' : 'none';

    const templateSection = $('account-template-section');
    if (mod.supports_template) {
      templateSection.style.display = '';
      $('account-template').value = state.editing.account.template || defaultTemplate(moduleName);
      renderTemplateTags(moduleName);
      updateTemplatePreview(moduleName);
    } else {
      templateSection.style.display = 'none';
    }

    $('account-modal').classList.add('active');
  }

  function buildAccountFieldHtml(mod, field) {
    const id = 'acc-' + mod.name + '-' + field.key;
    const raw = state.editing.account[field.key];
    const value = raw === undefined || raw === null ? '' : raw;

    if (field.type === 'bool') {
      return '<div class="form-group"><label class="switch">' +
        '<input type="checkbox" id="' + esc(id) + '"' + (value ? ' checked' : '') + '>' +
        esc(field.label) + '</label></div>';
    }

    const type = field.type === 'password' ? 'password' : (field.type === 'int' ? 'number' : 'text');
    const extra = field.type === 'password' ? ' autocomplete="new-password"' : '';

    return '<div class="form-group">' +
      '<label class="form-label" for="' + esc(id) + '">' + esc(field.label) + '</label>' +
      '<input class="form-input" type="' + type + '" id="' + esc(id) + '" value="' + esc(value) + '"' + extra + '>' +
      (field.hint ? '<div class="hint">' + esc(field.hint) + '</div>' : '') +
      '</div>';
  }

  function collectAccountForm(mod) {
    const account = {};

    (mod.account_fields || []).forEach((field) => {
      const el = $('acc-' + mod.name + '-' + field.key);
      if (!el) return;

      if (field.type === 'bool') {
        account[field.key] = el.checked;
      } else if (field.type === 'int') {
        account[field.key] = toInt(el.value, 0);
      } else {
        account[field.key] = el.value.trim();
      }
    });

    if (mod.supports_template) {
      const textarea = $('account-template');
      if (textarea) account.template = textarea.value;
    }

    return account;
  }

  /** 保存账号；失败时保持窗口打开并如实提示，不会出现"假成功" */
  async function saveAccount() {
    const editing = state.editing;
    if (!editing) return false;

    const mod = editing.module;
    const account = collectAccountForm(mod);

    const list = accountsOf(mod.name).slice();
    const index = list.findIndex((a) => a._filename === editing.filename);

    if (index >= 0) {
      account._filename = editing.filename;
      list[index] = account;
    } else {
      list.push(account);
    }

    try {
      await api.post('accounts', { platform: mod.name, accounts: list });
    } catch (e) {
      toast('保存失败：' + e.message, 'error');
      setStatus('保存失败：' + e.message, 'error');
      return false;
    }

    await refreshAccounts();
    return true;
  }

  /** 登录：需要模块声明 supports_login；测试不会写库，登录才会持久化凭据 */
  async function loginAccount() {
    const editing = state.editing;
    if (!editing) return;

    const mod = editing.module;

    if (!editing.filename) {
      setStatus('请先保存账号，再执行登录', 'warn');
      return;
    }

    const payload = { filename: editing.filename };
    ['account', 'password'].forEach((key) => {
      const el = $('acc-' + mod.name + '-' + key);
      if (el) payload[key] = el.value.trim();
    });

    const otp = $('account-otp').value.trim();
    if (otp) payload.otp_code = otp;

    setStatus('正在登录...', 'warn');

    try {
      const result = await api.post(mod.name + '/login', payload);

      if (result.status === 'otp_required') {
        $('account-otp-row').style.display = '';
        setStatus(result.message || '验证码已发送，请输入验证码后再次点击登录', 'warn');
        return;
      }

      setStatus(result.message || '登录成功', 'ok');
      await refreshAccounts();
    } catch (e) {
      setStatus('登录失败：' + e.message, 'error');
    }
  }

  async function testAccount() {
    const editing = state.editing;
    if (!editing) return;

    const mod = editing.module;
    setStatus('正在测试...', 'warn');

    try {
      const result = await api.post(mod.name + '/test', collectAccountForm(mod));
      setStatus(result.message || '测试成功', result.status === 'ok' ? 'ok' : 'error');
    } catch (e) {
      setStatus('测试失败：' + e.message, 'error');
    }
  }

  // ══════════════════════════════════════════
  //  模板编辑（统一 id，不再按平台拼 id，避免取不到元素）
  // ══════════════════════════════════════════

  function renderTemplateTags(moduleName) {
    const box = $('account-variable-tags');
    if (!box) return;

    box.innerHTML = variablesOf(moduleName)
      .filter((v) => v.show !== false)
      .map((v) => '<button class="variable-tag" data-action="insert-variable" data-name="' + esc(v.name) + '">' +
        esc(v.desc || v.name) + '</button>')
      .join('');
  }

  function updateTemplatePreview(moduleName) {
    const textarea = $('account-template');
    const preview = $('account-template-preview');
    if (!textarea || !preview) return;

    let text = textarea.value || defaultTemplate(moduleName);

    variablesOf(moduleName).forEach((v) => {
      text = text.split('{' + v.name + '}').join(v.default || '');
    });

    preview.textContent = text || '（请在左侧输入模板）';
  }

  function insertVariable(name) {
    const textarea = $('account-template');
    if (!textarea || !state.editing) return;

    const token = '{' + name + '}';
    const start = textarea.selectionStart || 0;
    const end = textarea.selectionEnd || 0;

    textarea.value = textarea.value.slice(0, start) + token + textarea.value.slice(end);
    textarea.selectionStart = textarea.selectionEnd = start + token.length;
    textarea.focus();

    updateTemplatePreview(state.editing.module.name);
  }

  // ══════════════════════════════════════════
  //  模块设置与变量保存
  // ══════════════════════════════════════════

  async function saveModuleConfig(moduleName) {
    const mod = moduleByName(moduleName);
    if (!mod) return;

    const payload = {};

    (mod.config_fields || []).forEach((field) => {
      const el = $('cfg-' + mod.name + '-' + field.key);
      if (!el) return;

      if (field.type === 'bool') {
        payload[field.key] = el.checked;
      } else if (field.type === 'int') {
        payload[field.key] = toInt(el.value, field.default === undefined ? 0 : field.default);
      } else {
        payload[field.key] = el.value.trim();
      }
    });

    try {
      await api.post(mod.name + '/config', payload);
      mod.config = Object.assign({}, mod.config, payload);
      toast('设置已保存');
    } catch (e) {
      toast('保存失败：' + e.message, 'error');
    }
  }

  async function saveVariables(moduleName) {
    const mod = moduleByName(moduleName);
    if (!mod) return;

    const rows = Array.from(document.querySelectorAll('#vars-' + moduleName + ' [data-var="name"]'));

    const variables = rows.map((el) => {
      const index = el.dataset.index;
      const pick = (key) => document.querySelector(
        '#vars-' + moduleName + ' [data-var="' + key + '"][data-index="' + index + '"]'
      );

      const descEl = pick('desc');
      const defaultEl = pick('default');
      const showEl = pick('show');

      return {
        name: el.value.trim(),
        desc: descEl ? descEl.value.trim() : '',
        default: defaultEl ? defaultEl.value : '',
        show: showEl ? showEl.checked : true,
      };
    }).filter((v) => v.name);

    try {
      await api.post('template-vars', { platform: moduleName, variables });
      await loadVars();
      renderVarTable(mod);
      renderTemplateTags(moduleName);
      toast('变量配置已保存');
    } catch (e) {
      toast('保存失败：' + e.message, 'error');
    }
  }

  /** 删除变量只改内存，需点「保存变量」才落库，误删可刷新恢复 */
  function removeVariable(moduleName, index) {
    const list = variablesOf(moduleName).slice();
    if (index < 0 || index >= list.length) return;

    list.splice(index, 1);
    state.vars[moduleName] = { variables: list };

    const mod = moduleByName(moduleName);
    if (mod) renderVarTable(mod);

    toast('已移除，点击「保存变量」后生效');
  }

  // ══════════════════════════════════════════
  //  删除账号
  // ══════════════════════════════════════════

  function askDelete(moduleName, filename, name) {
    state.pendingDelete = { module: moduleName, filename, name };
    $('delete-target').textContent = name || filename;
    $('delete-modal').classList.add('active');
  }

  async function confirmDelete() {
    const pending = state.pendingDelete;
    state.pendingDelete = null;
    closeModal('delete-modal');

    if (!pending) return;

    try {
      const result = await api.post('accounts/delete', {
        platform: pending.module,
        filename: pending.filename,
      });
      await refreshAccounts();
      toast('已删除「' + (result.deleted || pending.name) + '」');
    } catch (e) {
      toast('删除失败：' + e.message, 'error');
    }
  }

  // ══════════════════════════════════════════
  //  刷新
  // ══════════════════════════════════════════

  async function refreshAccounts() {
    try {
      await loadAccounts();
    } catch (e) {
      toast('账号列表刷新失败：' + e.message, 'error');
      return;
    }

    state.modules.forEach((mod) => {
      if (mod.supports_accounts) renderAccountList(mod);
    });
  }

  async function reloadAll() {
    await loadAll();

    if (!state.activeModule || !moduleByName(state.activeModule)) {
      state.activeModule = state.modules.length ? state.modules[0].name : '';
    }

    $('version').textContent = state.version ? 'v' + state.version : '';
    renderNav();
    renderPages();
  }

  function closeModal(id) {
    const el = $(id);
    if (el) el.classList.remove('active');
  }

  // ══════════════════════════════════════════
  //  事件绑定（委托，无内联事件）
  // ══════════════════════════════════════════

  async function onClick(event) {
    const target = event.target.closest('[data-action]');
    if (!target) return;

    const action = target.dataset.action;
    const moduleName = target.dataset.module;

    switch (action) {
      case 'select-module':
        selectModule(moduleName);
        break;

      case 'reload':
        await reloadAll();
        toast('已刷新');
        break;

      case 'add-account':
        openAccountModal(moduleName, '');
        break;

      case 'edit-account':
        openAccountModal(moduleName, target.dataset.file);
        break;

      case 'delete-account':
        askDelete(moduleName, target.dataset.file, target.dataset.name);
        break;

      case 'confirm-delete':
        await confirmDelete();
        break;

      case 'close-delete-modal':
        state.pendingDelete = null;
        closeModal('delete-modal');
        break;

      case 'close-account-modal':
        closeModal('account-modal');
        break;

      case 'save-account':
        if (await saveAccount()) {
          closeModal('account-modal');
          toast('已保存');
        }
        break;

      case 'login-account':
        await loginAccount();
        break;

      case 'test-account':
        await testAccount();
        break;

      case 'reset-template':
        if (state.editing) {
          $('account-template').value = defaultTemplate(state.editing.module.name);
          updateTemplatePreview(state.editing.module.name);
        }
        break;

      case 'insert-variable':
        insertVariable(target.dataset.name);
        break;

      case 'save-config':
        await saveModuleConfig(moduleName);
        break;

      case 'save-vars':
        await saveVariables(moduleName);
        break;

      case 'remove-var':
        removeVariable(moduleName, toInt(target.dataset.index, -1));
        break;

      default:
        break;
    }
  }

  function onInput(event) {
    if (event.target && event.target.id === 'account-template' && state.editing) {
      updateTemplatePreview(state.editing.module.name);
    }
  }

  function bindEvents() {
    document.addEventListener('click', onClick);
    document.addEventListener('input', onInput);

    // 点击遮罩关闭
    document.querySelectorAll('.modal-overlay').forEach((overlay) => {
      overlay.addEventListener('click', (e) => {
        if (e.target === overlay) closeModal(overlay.id);
      });
    });
  }

  // ══════════════════════════════════════════
  //  初始化
  // ══════════════════════════════════════════

  function showFatal(message) {
    const box = $('boot-error');
    if (box) box.innerHTML = '<div class="fatal">' + esc(message) + '</div>';
  }

  async function init() {
    if (!bridge) {
      showFatal('页面桥接未就绪（bridge SDK 未加载），请刷新页面重试。');
      return;
    }

    try {
      await bridge.ready();
    } catch (e) {
      showFatal('页面初始化失败：' + (e && e.message ? e.message : e));
      return;
    }

    bindEvents();
    await loadAll();

    if (state.modules.length) {
      state.activeModule = state.modules[0].name;
    }

    $('version').textContent = state.version ? 'v' + state.version : '';
    renderNav();
    renderPages();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
