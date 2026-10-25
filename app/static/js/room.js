/* 学生端座位交互：座位选择、前端状态筛选、日期/时间变化时通过 API 刷新座位。 */
(function () {
  'use strict';

  var DEFAULT_LABELS = { free: '空闲', taken: '已预约', mine: '我已预约', disabled: '不可用' };
  var KNOWN_STATUSES = ['free', 'taken', 'mine', 'disabled'];
  var SYNC_FIELDS = ['date', 'start', 'end'];
  var SEAT_HINT = '尚未选择座位，请在左侧座位图中点击空闲座位。';

  var grid = document.getElementById('seatGrid');
  if (!grid) {
    return;
  }

  var config = window.PAGE_CONFIG || {};
  var seatsUrl = config.seatsUrl || grid.getAttribute('data-seats-url') || '';
  if (!seatsUrl) {
    return;
  }

  var statusLabels = config.statusLabels || DEFAULT_LABELS;
  var seatInput = document.getElementById('seatIdInput');
  var selectedSeatLabel = document.getElementById('selectedSeatLabel');
  var messageArea = document.getElementById('seatStatusMessage');
  var bookingForm = document.getElementById('bookingForm');
  var filterButtons = toArray(document.querySelectorAll('.seat-filter__btn'));

  var state = {
    selectedSeatId: '',
    selectedSeatCode: '',
    filter: 'all',
    requestId: 0,
    reloadStarted: false
  };

  function toArray(nodeList) {
    return Array.prototype.slice.call(nodeList || []);
  }

  function each(nodeList, callback) {
    toArray(nodeList).forEach(callback);
  }

  function fieldNodes(name) {
    return toArray(document.querySelectorAll('[data-seat-field="' + name + '"]'));
  }

  function readField(name) {
    var nodes = fieldNodes(name);
    return nodes.length ? nodes[0].value : '';
  }

  function writeField(name, value) {
    each(fieldNodes(name), function (node) {
      if (node.value !== value) {
        node.value = value;
      }
    });
  }

  /* 读取当前查询条件，缺失时回退到服务端注入的初始配置。 */
  function currentState() {
    var values = {};
    SYNC_FIELDS.forEach(function (name) {
      var value = readField(name);
      if (!value) {
        if (name === 'date') {
          value = config.selectedDate || '';
        } else if (name === 'start') {
          value = config.startTime || '';
        } else {
          value = config.endTime || '';
        }
      }
      values[name] = value || '';
    });
    return values;
  }

  function statusLabel(status) {
    return statusLabels[status] || DEFAULT_LABELS[status] || status;
  }

  function announce(message, isError) {
    if (!messageArea) {
      return;
    }
    messageArea.textContent = message || '';
    messageArea.classList.toggle('text-danger', Boolean(isError));
  }

  function setSelectedLabel(seatCode, status) {
    if (!selectedSeatLabel) {
      return;
    }
    selectedSeatLabel.classList.remove('text-danger');
    if (status === 'mine') {
      selectedSeatLabel.textContent = '已选择座位 ' + seatCode + '，但你在该时段已有预约，请避免重复预约。';
    } else {
      selectedSeatLabel.textContent = '已选择座位 ' + seatCode + '。';
    }
  }

  function clearSelection() {
    state.selectedSeatId = '';
    state.selectedSeatCode = '';
    if (seatInput) {
      seatInput.value = '';
    }
    each(grid.querySelectorAll('.seat--selected'), function (button) {
      button.classList.remove('seat--selected');
      button.setAttribute('aria-pressed', 'false');
    });
    if (selectedSeatLabel) {
      selectedSeatLabel.textContent = SEAT_HINT;
      selectedSeatLabel.classList.remove('text-danger');
    }
  }

  function selectSeat(button) {
    var seatId = button.getAttribute('data-seat-id') || '';
    var seatCode = button.getAttribute('data-seat-code') || '';
    var status = button.getAttribute('data-status') || 'free';
    if (!seatId || (status !== 'free' && status !== 'mine')) {
      return;
    }
    if (!seatInput) {
      announce('请先登录，登录后即可选择座位并提交预约。', true);
      return;
    }
    if (state.selectedSeatId === seatId) {
      clearSelection();
      announce('已取消选择座位 ' + seatCode + '。');
      return;
    }
    each(grid.querySelectorAll('.seat--selected'), function (other) {
      other.classList.remove('seat--selected');
      other.setAttribute('aria-pressed', 'false');
    });
    state.selectedSeatId = seatId;
    state.selectedSeatCode = seatCode;
    seatInput.value = seatId;
    button.classList.add('seat--selected');
    button.setAttribute('aria-pressed', 'true');
    setSelectedLabel(seatCode, status);
    announce('已选择座位 ' + seatCode + (status === 'mine' ? '（该时段已有你的预约）' : '') + '。');
  }

  function findSeatButton(target) {
    var node = target;
    while (node && node !== grid) {
      if (node.classList && node.classList.contains('seat')) {
        return node;
      }
      node = node.parentNode;
    }
    return null;
  }

  function createSeatButton(seat) {
    var rawStatus = String(seat && seat.status ? seat.status : '');
    var status = KNOWN_STATUSES.indexOf(rawStatus) !== -1 ? rawStatus : 'disabled';
    var code = seat && seat.seat_code !== undefined && seat.seat_code !== null ? String(seat.seat_code) : '';
    var label = statusLabel(status);
    var button = document.createElement('button');
    button.type = 'button';
    button.className = 'seat seat--' + status;
    button.setAttribute('data-seat-id', seat && seat.id !== undefined && seat.id !== null ? String(seat.id) : '');
    button.setAttribute('data-seat-code', code);
    button.setAttribute('data-status', status);
    button.setAttribute('aria-pressed', 'false');
    button.setAttribute('aria-label', '座位 ' + code + '，' + label);
    if (status === 'taken' || status === 'disabled') {
      button.disabled = true;
      button.setAttribute('aria-disabled', 'true');
    }

    var codeEl = document.createElement('span');
    codeEl.className = 'seat__code';
    codeEl.textContent = code;
    var noteEl = document.createElement('span');
    noteEl.className = 'seat__note';
    noteEl.textContent = label;
    button.appendChild(codeEl);
    button.appendChild(noteEl);

    if (state.selectedSeatId && state.selectedSeatId === button.getAttribute('data-seat-id')) {
      button.classList.add('seat--selected');
      button.setAttribute('aria-pressed', 'true');
    }
    return button;
  }

  function createEmptyState() {
    var wrapper = document.createElement('div');
    wrapper.className = 'empty-state';
    var icon = document.createElement('div');
    icon.className = 'empty-state__icon';
    icon.setAttribute('aria-hidden', 'true');
    icon.textContent = '🪑';
    var title = document.createElement('h3');
    title.className = 'empty-state__title';
    title.textContent = '该时间段暂无可用座位';
    var text = document.createElement('p');
    text.className = 'empty-state__text';
    text.textContent = '请调整日期或时间段后重试。';
    wrapper.appendChild(icon);
    wrapper.appendChild(title);
    wrapper.appendChild(text);
    return wrapper;
  }

  function renderSeats(seats) {
    var list = seats || [];
    if (state.selectedSeatId) {
      var selectedSeat = null;
      list.forEach(function (seat) {
        if (seat && seat.id !== undefined && String(seat.id) === state.selectedSeatId) {
          selectedSeat = seat;
        }
      });
      var stillSelectable = selectedSeat && (selectedSeat.status === 'free' || selectedSeat.status === 'mine');
      if (!stillSelectable) {
        clearSelection();
        announce('所选座位在当前时间段已不可预约，请重新选择。', true);
      }
    }

    grid.textContent = '';
    if (!list.length) {
      grid.appendChild(createEmptyState());
    } else {
      var fragment = document.createDocumentFragment();
      list.forEach(function (seat) {
        fragment.appendChild(createSeatButton(seat));
      });
      grid.appendChild(fragment);
    }

    applyFilter(state.filter, true);

    if (state.selectedSeatId) {
      var selectedButton = grid.querySelector('.seat--selected');
      if (selectedButton) {
        setSelectedLabel(selectedButton.getAttribute('data-seat-code'), selectedButton.getAttribute('data-status'));
      }
    }
  }

  function updateCounts(counts) {
    if (!counts) {
      return;
    }
    each(document.querySelectorAll('[data-count]'), function (element) {
      var key = element.getAttribute('data-count');
      if (Object.prototype.hasOwnProperty.call(counts, key) && counts[key] !== null && counts[key] !== undefined) {
        element.textContent = String(counts[key]);
      }
    });
  }

  function applyFilter(status, silent) {
    var nextStatus = status || 'all';
    state.filter = nextStatus;
    each(grid.querySelectorAll('.seat'), function (button) {
      var visible = nextStatus === 'all' || button.getAttribute('data-status') === nextStatus;
      button.classList.toggle('seat--hidden', !visible);
    });
    filterButtons.forEach(function (button) {
      var active = button.getAttribute('data-status') === nextStatus;
      button.classList.toggle('seat-filter__btn--active', active);
      button.setAttribute('aria-pressed', active ? 'true' : 'false');
    });
    if (!silent) {
      announce(nextStatus === 'all' ? '已显示全部座位。' : '已筛选：' + statusLabel(nextStatus) + '座位。');
    }
  }

  function buildSeatsUrl() {
    var values = currentState();
    var separator = seatsUrl.indexOf('?') === -1 ? '?' : '&';
    return seatsUrl + separator +
      'date=' + encodeURIComponent(values.date) +
      '&start=' + encodeURIComponent(values.start) +
      '&end=' + encodeURIComponent(values.end);
  }

  function buildPageUrl() {
    var values = currentState();
    var url = new URL(window.location.href);
    url.searchParams.set('date', values.date);
    url.searchParams.set('start', values.start);
    url.searchParams.set('end', values.end);
    return url.pathname + url.search;
  }

  /* 座位接口不可用（HTTP 错误或网络错误）时，降级为整页刷新并按当前条件重建 query。 */
  function fallbackToFullReload(error) {
    if (state.reloadStarted) {
      return;
    }
    state.reloadStarted = true;
    if (window.console && window.console.warn) {
      window.console.warn('[room.js] 座位状态刷新失败，降级为整页刷新：', error);
    }
    announce('座位状态刷新失败，正在重新加载页面…', true);
    window.setTimeout(function () {
      try {
        window.location.assign(buildPageUrl());
      } catch (buildError) {
        window.location.reload();
      }
    }, 400);
  }

  function refreshSeats() {
    state.requestId += 1;
    var requestId = state.requestId;
    grid.setAttribute('aria-busy', 'true');
    announce('正在刷新座位状态…');

    fetch(buildSeatsUrl(), {
      method: 'GET',
      credentials: 'same-origin',
      cache: 'no-store',
      headers: {
        Accept: 'application/json',
        'X-Requested-With': 'XMLHttpRequest'
      }
    })
      .then(function (response) {
        if (!response.ok) {
          throw new Error('HTTP ' + response.status);
        }
        return response.json();
      })
      .then(function (data) {
        if (requestId !== state.requestId) {
          return;
        }
        if (!data || !Array.isArray(data.seats)) {
          throw new Error('响应数据格式不正确');
        }
        renderSeats(data.seats);
        updateCounts(data.counts);
        announce('座位状态已更新，点击空闲座位即可选择。');
      })
      .catch(function (error) {
        if (requestId !== state.requestId) {
          return;
        }
        fallbackToFullReload(error);
      })
      .then(function () {
        if (requestId === state.requestId) {
          grid.removeAttribute('aria-busy');
        }
      });
  }

  /* 日期/时间控件（查询表单与预约表单各有一组）保持同步。 */
  document.addEventListener('change', function (event) {
    var target = event.target;
    if (!target || typeof target.getAttribute !== 'function') {
      return;
    }
    var field = target.getAttribute('data-seat-field');
    if (SYNC_FIELDS.indexOf(field) === -1) {
      return;
    }
    writeField(field, target.value);
    refreshSeats();
  });

  grid.addEventListener('click', function (event) {
    var button = findSeatButton(event.target);
    if (!button || button.disabled) {
      return;
    }
    selectSeat(button);
  });

  filterButtons.forEach(function (button) {
    button.addEventListener('click', function () {
      applyFilter(button.getAttribute('data-status'));
    });
  });

  if (bookingForm) {
    bookingForm.addEventListener('submit', function (event) {
      if (seatInput && seatInput.value) {
        var values = currentState();
        SYNC_FIELDS.forEach(function (name) {
          writeField(name, values[name]);
        });
        return;
      }
      event.preventDefault();
      if (selectedSeatLabel) {
        selectedSeatLabel.textContent = '请先点击选择一个空闲座位，再提交预约。';
        selectedSeatLabel.classList.add('text-danger');
      }
      announce('请先选择座位。', true);
      var firstFreeSeat = grid.querySelector('.seat--free');
      if (firstFreeSeat) {
        firstFreeSeat.focus();
      }
    });
  }

  applyFilter('all', true);
})();
