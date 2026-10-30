// 资源查询插件 Views 前端：导航、模块页面、配置表单、账号卡与变量表渲染
//
// 所有脚本共享同一全局作用域，按 index.html 中的顺序加载；
// 工具与状态由 base.js 提供。
'use strict';

  //  渲染：导航

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

  function selectModule(name) {
    state.activeModule = name;

    document.querySelectorAll('.nav-tab').forEach((tab) => {
      tab.classList.toggle('active', tab.dataset.module === name);
    });

    document.querySelectorAll('.page').forEach((page) => {
      page.classList.toggle('active', page.id === 'page-' + name);
    });
  }

  //  渲染：模块页面（含页面标签）

  /** 模块可用的页面标签 */
  function moduleTabs(mod) {
    const tabs = [];
    if (mod.supports_accounts) tabs.push({ key: 'accounts', label: '账号管理' });
    if (Object.keys(mod.variables || {}).length) tabs.push({ key: 'variables', label: '模板变量' });
    if ((mod.config_fields || []).length) tabs.push({ key: 'settings', label: '模块设置' });
    return tabs;
  }

  function currentSubTab(mod) {
    const tabs = moduleTabs(mod);
    if (!tabs.length) return '';

    const saved = state.subTabs[mod.name];
    return tabs.some((t) => t.key === saved) ? saved : tabs[0].key;
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

  function buildPageHtml(mod) {
    const parts = [
      '<div class="module-head">' +
        '<h2>' + esc((mod.icon ? mod.icon + ' ' : '') + mod.title) + '</h2>' +
        (mod.desc ? '<p>' + esc(mod.desc) + '</p>' : '') +
      '</div>',
    ];

    const tabs = moduleTabs(mod);

    if (!tabs.length) {
      parts.push('<div class="card"><div class="card-body"><div class="empty">该模块没有可配置的内容</div></div></div>');
      return parts.join('');
    }

    const active = currentSubTab(mod);

    parts.push('<div class="sub-tabs">' + tabs.map((t) =>
      '<button class="sub-tab' + (t.key === active ? ' active' : '') + '"' +
      ' data-action="select-subtab" data-module="' + esc(mod.name) + '" data-tab="' + esc(t.key) + '">' +
      esc(t.label) + '</button>'
    ).join('') + '</div>');

    tabs.forEach((t) => {
      parts.push(
        '<div class="sub-page' + (t.key === active ? ' active' : '') + '"' +
        ' id="sub-' + esc(mod.name) + '-' + esc(t.key) + '">' +
        buildSubPageHtml(mod, t.key) +
        '</div>'
      );
    });

    return parts.join('');
  }

  function buildSubPageHtml(mod, tabKey) {
    if (tabKey === 'accounts') {
      return '<div class="card">' +
        '<div class="card-header">' +
          '<span class="card-title">账号列表</span>' +
          '<button class="btn btn-primary btn-sm" data-action="add-account" data-module="' + esc(mod.name) + '">＋ 添加账号</button>' +
        '</div>' +
        '<div class="card-body"><div class="account-grid" id="list-' + esc(mod.name) + '"></div></div>' +
        '</div>';
    }

    if (tabKey === 'variables') {
      return '<div class="card">' +
        '<div class="card-header">' +
          '<span class="card-title">模板变量</span>' +
          '<button class="btn btn-primary btn-sm" data-action="save-vars" data-module="' + esc(mod.name) + '">保存变量</button>' +
        '</div>' +
        '<div class="card-body"><div class="table-scroll"><table class="var-table">' +
          '<thead><tr><th>变量名</th><th>说明</th><th>示例值</th><th>显示</th><th></th></tr></thead>' +
          '<tbody id="vars-' + esc(mod.name) + '"></tbody>' +
        '</table></div></div>' +
        '</div>';
    }

    return '<div class="card">' +
      '<div class="card-header">' +
        '<span class="card-title">模块设置</span>' +
        '<button class="btn btn-primary btn-sm" data-action="save-config" data-module="' + esc(mod.name) + '">保存设置</button>' +
      '</div>' +
      '<div class="card-body">' + buildConfigFieldsHtml(mod) + '</div>' +
      '</div>';
  }

  function selectSubTab(moduleName, tabKey) {
    state.subTabs[moduleName] = tabKey;

    const mod = moduleByName(moduleName);
    if (!mod) return;

    moduleTabs(mod).forEach((t) => {
      const btn = document.querySelector(
        '.sub-tab[data-action="select-subtab"][data-module="' + moduleName + '"][data-tab="' + t.key + '"]'
      );
      if (btn) btn.classList.toggle('active', t.key === tabKey);

      const pane = $('sub-' + moduleName + '-' + t.key);
      if (pane) pane.classList.toggle('active', t.key === tabKey);
    });
  }

  function buildConfigFieldsHtml(mod) {
    const config = mod.config || {};

    return (mod.config_fields || []).map((field) => {
      const raw = config[field.key];
      const value = raw === undefined ? (field.default === undefined ? '' : field.default) : raw;
      const id = 'cfg-' + mod.name + '-' + field.key;

      if (field.type === 'bool') {
        return '<div class="form-group">' + fieldInputHtml(id, field, value) +
          (field.hint ? '<div class="hint">' + esc(field.hint) + '</div>' : '') +
          '</div>';
      }

      const label = '<label class="form-label" for="' + esc(id) + '">' + esc(field.label) + '</label>';

      return '<div class="form-group">' +
        label +
        fieldInputHtml(id, field, value) +
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

      return '<div class="account-card" data-action="edit-account" ' +
          'data-module="' + esc(mod.name) + '" data-file="' + esc(acc._filename || '') + '">' +
        '<div class="account-main">' +
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
