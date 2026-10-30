// 资源查询插件 Views 前端：账号模态框、保存 / 登录 / 测试与删除
//
// 所有脚本共享同一全局作用域，按 index.html 中的顺序加载；
// 工具与状态由 base.js 提供。
'use strict';

  //  账号模态框

  function openAccountModal(moduleName, filename) {
    const mod = moduleByName(moduleName);
    if (!mod) return;

    const account = filename
      ? accountsOf(moduleName).find((a) => a._filename === filename)
      : null;

    const tabGroups = accountTabGroups(mod);

    state.editing = {
      module: mod,
      filename: filename || '',
      account: Object.assign({}, account || {}),
      activeTab: 'config',
      activeGroup: tabGroups.length ? tabGroups[0].key : '',
    };

    $('account-modal-title').textContent = (account ? '编辑 ' : '添加 ') + mod.title + ' 账号';

    setStatus('');
    $('account-otp').value = '';
    $('account-otp-row').style.display = 'none';

    const btnLogin = $('btn-login');
    btnLogin.style.display = mod.supports_login ? '' : 'none';
    btnLogin.disabled = !account;
    btnLogin.title = account ? '' : '请先保存账号，再执行登录';

    $('btn-test').style.display = mod.supports_test ? '' : 'none';

    renderAccountModalBody();
    $('account-modal').classList.add('active');
  }

  /** 模态框骨架：账号配置 / 消息模板 两个标签 */
  function renderAccountModalBody() {
    const editing = state.editing;
    if (!editing) return;

    const mod = editing.module;
    const tabs = [{ key: 'config', label: '账号配置' }];
    if (mod.supports_template) tabs.push({ key: 'template', label: '消息模板' });

    $('account-tabs').innerHTML = tabs.map((t) =>
      '<button class="sub-tab' + (t.key === editing.activeTab ? ' active' : '') + '"' +
      ' data-action="select-account-tab" data-tab="' + esc(t.key) + '">' + esc(t.label) + '</button>'
    ).join('');

    $('account-pane-config').style.display = editing.activeTab === 'config' ? '' : 'none';
    $('account-pane-template').style.display = editing.activeTab === 'template' ? '' : 'none';

    if (editing.activeTab === 'config') {
      renderAccountForm();
    } else {
      $('account-template').value = editing.account.template || defaultTemplate(mod.name);
      renderTemplateTags(mod.name);
      updateTemplatePreview(mod.name);
    }
  }

  /** 渲染账号配置：顶部为公共字段，中间为凭据方式标签，底部为内联分组 */
  function renderAccountForm() {
    const editing = state.editing;
    if (!editing) return;

    const mod = editing.module;
    const fields = mod.account_fields || [];
    const parts = [];

    const base = ungroupedFields(mod);
    if (base.length) {
      parts.push(base.map((field) => buildAccountFieldHtml(mod, field)).join(''));
    }

    const tabGroups = accountTabGroups(mod);
    if (tabGroups.length) {
      let active = tabGroups.find((g) => g.key === editing.activeGroup);
      if (!active) {
        active = tabGroups[0];
        editing.activeGroup = active.key;
      }

      parts.push('<div class="sub-tabs">' + tabGroups.map((g) =>
        '<button class="sub-tab' + (g.key === active.key ? ' active' : '') + '"' +
        ' data-action="select-group" data-group="' + esc(g.key) + '">' + esc(g.label) + '</button>'
      ).join('') + '</div>');

      if (active.hint) {
        parts.push('<div class="group-hint">' + esc(active.hint) + '</div>');
      }

      parts.push(fieldsInGroup(fields, active.key).map((field) => buildAccountFieldHtml(mod, field)).join(''));
    }

    accountInlineGroups(mod).forEach((group) => {
      parts.push('<div class="field-block">');
      parts.push('<div class="field-block-head"><span>' + esc(group.label) + '</span></div>');
      if (group.hint) parts.push('<div class="hint">' + esc(group.hint) + '</div>');
      parts.push(fieldsInGroup(fields, group.key).map((field) => buildAccountFieldHtml(mod, field)).join(''));
      parts.push('</div>');
    });

    $('account-form').innerHTML = parts.join('');
  }

  /** 字段标签行（字段带默认值时附带「恢复默认」按钮） */
  function fieldLabelHtml(id, field) {
    const reset = field.default !== undefined
      ? '<button class="btn btn-ghost btn-sm field-reset" data-action="reset-field" ' +
        'data-key="' + esc(field.key) + '" title="恢复为插件默认值">↺ 恢复默认</button>'
      : '';

    return '<div class="form-label-row">' +
      '<label class="form-label" for="' + esc(id) + '">' + esc(field.label) + '</label>' +
      reset +
      '</div>';
  }

  /** 输入控件；密码类型带显示 / 隐藏切换 */
  function fieldInputHtml(id, field, value) {
    if (field.type === 'bool') {
      return '<label class="switch"><input type="checkbox" id="' + esc(id) + '"' +
        (value ? ' checked' : '') + '>' + esc(field.label) + '</label>';
    }

    const isPassword = field.type === 'password';
    const type = isPassword ? 'password' : (field.type === 'int' ? 'number' : 'text');
    const extra = isPassword ? ' autocomplete="new-password"' : '';

    const input = '<input class="form-input" type="' + type + '" id="' + esc(id) + '" value="' +
      esc(value) + '"' + extra + '>';

    if (!isPassword) return input;

    return '<div class="pw-wrapper">' + input +
      '<button type="button" class="pw-toggle" data-action="toggle-password" ' +
      'data-target="' + esc(id) + '" title="显示 / 隐藏">显示</button>' +
      '</div>';
  }

  function buildAccountFieldHtml(mod, field) {
    const id = 'acc-' + mod.name + '-' + field.key;
    const raw = state.editing.account[field.key];
    const value = raw === undefined || raw === null ? '' : raw;

    if (field.type === 'bool') {
      return '<div class="form-group">' + fieldInputHtml(id, field, value) + '</div>';
    }

    return '<div class="form-group">' +
      fieldLabelHtml(id, field) +
      fieldInputHtml(id, field, value) +
      (field.hint ? '<div class="hint">' + esc(field.hint) + '</div>' : '') +
      '</div>';
  }

  /** 把当前已渲染的输入值写回数据模型（切换标签前必须调用，避免取值丢失） */
  function syncAccountForm() {
    const editing = state.editing;
    if (!editing) return;

    const mod = editing.module;

    (mod.account_fields || []).forEach((field) => {
      const el = $('acc-' + mod.name + '-' + field.key);
      if (!el) return;

      if (field.type === 'bool') {
        editing.account[field.key] = el.checked;
      } else if (field.type === 'int') {
        editing.account[field.key] = toInt(el.value, 0);
      } else {
        editing.account[field.key] = el.value.trim();
      }
    });

    if (mod.supports_template) {
      const textarea = $('account-template');
      if (textarea) editing.account.template = textarea.value;
    }
  }

  /** 以当前数据模型重建「账号配置」内容（切换凭据方式时调用） */
  function selectGroup(groupKey) {
    const editing = state.editing;
    if (!editing) return;

    syncAccountForm();
    editing.activeGroup = groupKey;
    renderAccountForm();
  }

  function selectAccountTab(tabKey) {
    const editing = state.editing;
    if (!editing) return;

    syncAccountForm();
    editing.activeTab = tabKey;
    renderAccountModalBody();
  }

  /** 把单个字段恢复为插件默认值（设备标识、User-Agent 可分别重置） */
  function resetField(fieldKey) {
    const editing = state.editing;
    if (!editing) return;

    const field = (editing.module.account_fields || []).find((f) => f.key === fieldKey);
    if (!field || field.default === undefined) return;

    syncAccountForm();
    editing.account[fieldKey] = field.default;
    renderAccountForm();
    toast('已恢复默认值');
  }

  /** 保存账号；失败时保持窗口打开并如实提示，不会出现"假成功" */
  async function saveAccount() {
    const editing = state.editing;
    if (!editing) return false;

    syncAccountForm();

    const mod = editing.module;
    const account = Object.assign({}, editing.account);
    delete account._filename;

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

    syncAccountForm();

    const payload = {
      filename: editing.filename,
      account: editing.account.account || '',
      password: editing.account.password || '',
    };

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
    syncAccountForm();

    const payload = Object.assign({}, editing.account);
    delete payload._filename;

    setStatus('正在测试...', 'warn');

    try {
      const result = await api.post(mod.name + '/test', payload);
      setStatus(result.message || '测试成功', result.status === 'ok' ? 'ok' : 'error');
    } catch (e) {
      setStatus('测试失败：' + e.message, 'error');
    }
  }

  //  删除账号

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
