/* global Chart */
/**
 * 管理端统计分析页图表脚本。
 * - 数据来源：页面内嵌的 <script type="application/json" id="statisticsData">
 * - 图表库：本地 vendor/chart.umd.min.js（Chart.js 4.x），不依赖任何 CDN
 * - 降级：图表库缺失 / 数据为空 / JSON 解析失败 / 绘制异常时，不抛出异常，
 *   改为显示 .chart-fallback 提示文本；服务端已为每张图渲染数据表格。
 */
(function () {
  'use strict';

  var PRIMARY = '#1d4ed8';
  var PRIMARY_SOFT = 'rgba(29, 78, 216, 0.14)';
  var PRIMARY_BAR = 'rgba(29, 78, 216, 0.8)';
  var GRID_COLOR = 'rgba(148, 163, 184, 0.28)';
  var TEXT_COLOR = '#475569';
  var FONT_FAMILY = '-apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", "PingFang SC", "Helvetica Neue", Arial, sans-serif';

  function readStatisticsData() {
    var node = document.getElementById('statisticsData');
    if (!node) {
      return null;
    }
    var raw = (node.textContent || '').replace(/^\s+|\s+$/g, '');
    if (!raw) {
      return null;
    }
    try {
      return JSON.parse(raw);
    } catch (firstError) {
      // 兼容 Jinja 自动转义后产生的 HTML 实体（&#34; 等）
      try {
        return JSON.parse(decodeHtmlEntities(raw));
      } catch (secondError) {
        return null;
      }
    }
  }

  function decodeHtmlEntities(text) {
    if (!text || text.indexOf('&') === -1) {
      return text;
    }
    var textarea = document.createElement('textarea');
    textarea.innerHTML = text;
    return textarea.value;
  }

  function toArray(value) {
    return Object.prototype.toString.call(value) === '[object Array]' ? value : [];
  }

  function toNumber(value) {
    var num = Number(value);
    return isFinite(num) ? num : 0;
  }

  function toPercentValue(value) {
    return Math.round(toNumber(value) * 10) / 10;
  }

  function revealFallback(fallback, message) {
    if (!fallback) {
      return;
    }
    if (message) {
      fallback.textContent = message;
    }
    // .chart-fallback 使用 display:flex 布局，会覆盖 [hidden] 的默认样式，这里同时重置内联样式。
    fallback.hidden = false;
    fallback.style.display = 'flex';
  }

  function hideChartBox(canvas) {
    var box = canvas.closest ? canvas.closest('.chart-box') : canvas.parentNode;
    if (box) {
      box.style.display = 'none';
    }
    canvas.style.display = 'none';
  }

  function showFallbacks(message) {
    var fallbacks = document.querySelectorAll('[data-chart-fallback]');
    for (var i = 0; i < fallbacks.length; i += 1) {
      revealFallback(fallbacks[i], message);
    }
    var boxes = document.querySelectorAll('.chart-box');
    for (var j = 0; j < boxes.length; j += 1) {
      boxes[j].style.display = 'none';
    }
  }

  function showCardFallback(canvas, message) {
    var card = canvas.parentNode;
    while (card && card !== document.body) {
      if (card.classList && card.classList.contains('chart-card')) {
        break;
      }
      card = card.parentNode;
    }
    var fallback = card ? card.querySelector('[data-chart-fallback]') : null;
    revealFallback(fallback, message);
    hideChartBox(canvas);
  }

  function setupDefaults() {
    if (window.Chart && window.Chart.defaults) {
      window.Chart.defaults.font.family = FONT_FAMILY;
      window.Chart.defaults.font.size = 12;
      window.Chart.defaults.color = TEXT_COLOR;
    }
  }

  function buildUtilizationChart(canvas, dailyTrend) {
    var labels = [];
    var values = [];
    for (var i = 0; i < dailyTrend.length; i += 1) {
      labels.push(dailyTrend[i].label || dailyTrend[i].date || '');
      values.push(toPercentValue(dailyTrend[i].utilization));
    }
    return new Chart(canvas.getContext('2d'), {
      type: 'line',
      data: {
        labels: labels,
        datasets: [{
          label: '座位利用率（%）',
          data: values,
          borderColor: PRIMARY,
          backgroundColor: PRIMARY_SOFT,
          borderWidth: 2,
          fill: true,
          tension: 0.35,
          pointRadius: 4,
          pointHoverRadius: 6,
          pointBackgroundColor: '#ffffff',
          pointBorderColor: PRIMARY,
          pointBorderWidth: 2
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: function (context) {
                return '座位利用率：' + Number(context.parsed.y).toFixed(1) + '%';
              }
            }
          }
        },
        scales: {
          y: {
            beginAtZero: true,
            suggestedMax: 100,
            ticks: {
              callback: function (value) {
                return value + '%';
              }
            },
            grid: { color: GRID_COLOR }
          },
          x: {
            grid: { display: false }
          }
        }
      }
    });
  }

  function buildHourlyChart(canvas, hourly) {
    var labels = [];
    var counts = [];
    for (var i = 0; i < hourly.length; i += 1) {
      labels.push(hourly[i].label || (toNumber(hourly[i].hour) + ':00'));
      counts.push(Math.round(toNumber(hourly[i].count)));
    }
    return new Chart(canvas.getContext('2d'), {
      type: 'bar',
      data: {
        labels: labels,
        datasets: [{
          label: '预约数量（条）',
          data: counts,
          backgroundColor: PRIMARY_BAR,
          borderRadius: 6,
          maxBarThickness: 48
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: function (context) {
                return '预约数量：' + Math.round(Number(context.parsed.y)) + ' 条';
              }
            }
          }
        },
        scales: {
          y: {
            beginAtZero: true,
            ticks: { precision: 0 },
            grid: { color: GRID_COLOR }
          },
          x: {
            grid: { display: false }
          }
        }
      }
    });
  }

  function buildRoomsChart(canvas, rooms) {
    var labels = [];
    var counts = [];
    for (var i = 0; i < rooms.length; i += 1) {
      labels.push(rooms[i].name || ('自习室 #' + toNumber(rooms[i].room_id)));
      counts.push(Math.round(toNumber(rooms[i].reservations)));
    }
    return new Chart(canvas.getContext('2d'), {
      type: 'bar',
      data: {
        labels: labels,
        datasets: [{
          label: '预约数量（条）',
          data: counts,
          backgroundColor: PRIMARY_BAR,
          borderRadius: 6,
          maxBarThickness: 28
        }]
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: function (context) {
                return '预约数量：' + Math.round(Number(context.parsed.x)) + ' 条';
              }
            }
          }
        },
        scales: {
          x: {
            beginAtZero: true,
            ticks: { precision: 0 },
            grid: { color: GRID_COLOR }
          },
          y: {
            grid: { display: false }
          }
        }
      }
    });
  }

  function renderChart(canvasId, series, builder, emptyMessage) {
    var canvas = document.getElementById(canvasId);
    if (!canvas || typeof canvas.getContext !== 'function') {
      return;
    }
    if (!series || !series.length) {
      showCardFallback(canvas, emptyMessage);
      return;
    }
    try {
      builder(canvas, series);
    } catch (error) {
      showCardFallback(canvas, '图表渲染失败，已提供数据表格作为替代。');
      if (window.console && typeof window.console.warn === 'function') {
        window.console.warn('[statistics.js] 图表渲染失败：', error);
      }
    }
  }

  function init() {
    var data = readStatisticsData();
    if (!data) {
      showFallbacks('统计数据加载失败，已提供数据表格作为替代。');
      return;
    }

    var hasData = data.has_data !== undefined && data.has_data !== null
      ? !!data.has_data
      : !!(toArray(data.daily_trend).length || toArray(data.hourly).length || toArray(data.rooms).length);

    // 无数据时服务端已渲染 .chart-empty，不绘制任何假数据。
    if (!hasData) {
      return;
    }

    if (!window.Chart || typeof window.Chart !== 'function') {
      showFallbacks('图表库不可用，已提供数据表格作为替代。');
      return;
    }

    setupDefaults();

    renderChart('chartUtilization', toArray(data.daily_trend), buildUtilizationChart, '暂无利用率数据，已提供数据表格作为替代。');
    renderChart('chartHourly', toArray(data.hourly), buildHourlyChart, '暂无时段数据，已提供数据表格作为替代。');
    renderChart('chartRooms', toArray(data.rooms), buildRoomsChart, '暂无自习室数据，已提供数据表格作为替代。');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
