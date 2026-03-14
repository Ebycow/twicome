(function () {
  // markVisited
  var userEl = document.getElementById('user-data');
  var rootPathEl = document.getElementById('root-path-data');
  if (userEl && rootPathEl && window.TwicomeOfflineAccess) {
    var rawRootPath = JSON.parse(rootPathEl.textContent);
    var rootPathForMark = (typeof rawRootPath === 'string' && rawRootPath && rawRootPath !== '/') ? rawRootPath.replace(/\/+$/, '') : '';
    var userLogin = JSON.parse(userEl.textContent);
    window.TwicomeOfflineAccess.markVisited(rootPathForMark, 'stats', userLogin);
  }

  var isDarkMode = window.matchMedia('(prefers-color-scheme: dark)').matches;
  var textColor = isDarkMode ? '#e0e0e0' : '#666';
  var gridColor = isDarkMode ? '#444' : '#ddd';

  // ---- コミュニティノート ----
  var cnScoresEl = document.getElementById('cn-scores-data');
  if (cnScoresEl) {
    var cnScores = JSON.parse(cnScoresEl.textContent);

    var distLabels = ['0-9', '10-19', '20-29', '30-39', '40-49', '50-59', '60-69', '70-79', '80-89', '90-100'];
    var distColors = cnScores.danger_dist.map(function (_, i) {
      if (i < 3) return 'rgba(76,175,80,0.6)';
      if (i < 6) return 'rgba(255,152,0,0.6)';
      return 'rgba(244,67,54,0.6)';
    });
    var distBorders = cnScores.danger_dist.map(function (_, i) {
      if (i < 3) return '#4caf50';
      if (i < 6) return '#ff9800';
      return '#f44336';
    });
    new Chart(document.getElementById('dangerDistChart').getContext('2d'), {
      type: 'bar',
      data: {
        labels: distLabels,
        datasets: [{
          label: 'コメント数',
          data: cnScores.danger_dist,
          backgroundColor: distColors,
          borderColor: distBorders,
          borderWidth: 1
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          y: {
            beginAtZero: true,
            ticks: { color: textColor, precision: 0 },
            grid: { color: gridColor },
            title: { display: true, text: '件数', color: textColor }
          },
          x: {
            ticks: { color: textColor },
            grid: { color: gridColor },
            title: { display: true, text: '危険度', color: textColor }
          }
        },
        plugins: { legend: { display: false } }
      }
    });

    var ctxRadar = document.getElementById('cnRadarChart').getContext('2d');
    new Chart(ctxRadar, {
      type: 'radar',
      data: {
        labels: ['検証可能性', '被害可能性', '誇張度', '根拠不足', '主観度'],
        datasets: [{
          label: '平均スコア',
          data: [
            cnScores.avg_verifiability,
            cnScores.avg_harm_risk,
            cnScores.avg_exaggeration,
            cnScores.avg_evidence_gap,
            cnScores.avg_subjectivity
          ],
          backgroundColor: 'rgba(255, 99, 132, 0.2)',
          borderColor: 'rgba(255, 99, 132, 1)',
          borderWidth: 2,
          pointBackgroundColor: 'rgba(255, 99, 132, 1)',
          pointBorderColor: '#fff',
          pointRadius: 4
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          r: {
            beginAtZero: true,
            max: 100,
            ticks: { stepSize: 20, color: textColor, backdropColor: 'transparent' },
            grid: { color: gridColor },
            angleLines: { color: gridColor },
            pointLabels: { color: textColor, font: { size: 13 } }
          }
        },
        plugins: { legend: { display: false } }
      }
    });
  }

  var stats = JSON.parse(document.getElementById('stats-data').textContent);
  var ctx = document.getElementById('statsChart').getContext('2d');
  new Chart(ctx, {
    type: 'bar',
    data: {
      labels: Array.from({length: 24}, function (_, i) { return i + ':00'; }),
      datasets: [{
        label: 'コメント数',
        data: stats,
        backgroundColor: 'rgba(54, 162, 235, 0.4)',
        borderColor: 'rgba(54, 162, 235, 1)',
        borderWidth: 1
      }]
    },
    options: {
      maintainAspectRatio: false,
      scales: {
        y: { beginAtZero: true, ticks: { color: textColor }, grid: { color: gridColor } },
        x: { ticks: { color: textColor }, grid: { color: gridColor } }
      },
      plugins: { legend: { labels: { color: textColor } } }
    }
  });

  var weekdayStats = JSON.parse(document.getElementById('weekday-stats-data').textContent);
  var ctxWeekday = document.getElementById('weekdayChart').getContext('2d');
  new Chart(ctxWeekday, {
    type: 'doughnut',
    data: {
      labels: ['日曜日', '月曜日', '火曜日', '水曜日', '木曜日', '金曜日', '土曜日'],
      datasets: [{
        label: 'コメント数',
        data: weekdayStats,
        backgroundColor: [
          'rgba(255, 99, 132, 0.4)', 'rgba(54, 162, 235, 0.4)', 'rgba(255, 205, 86, 0.4)',
          'rgba(75, 192, 192, 0.4)', 'rgba(153, 102, 255, 0.4)', 'rgba(255, 159, 64, 0.4)',
          'rgba(199, 199, 199, 0.4)'
        ],
        borderColor: [
          'rgba(255, 99, 132, 1)', 'rgba(54, 162, 235, 1)', 'rgba(255, 205, 86, 1)',
          'rgba(75, 192, 192, 1)', 'rgba(153, 102, 255, 1)', 'rgba(255, 159, 64, 1)',
          'rgba(199, 199, 199, 1)'
        ],
        borderWidth: 1
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: 'top', labels: { color: textColor } },
        title: { display: true, text: '曜日ごとのコメント数', color: textColor }
      }
    }
  });

  // ---- 配信者アクティブ状況テーブルのソート ----
  var ownersTable = document.getElementById('ownersTable');
  if (ownersTable) {
    var ownersBody = ownersTable.tBodies[0];
    var ownerHeaders = Array.from(ownersTable.querySelectorAll('th.sortable'));
    var currentSortKey = null;
    var currentSortDir = null;

    var numFromCell = function (row, cellIndex) {
      var raw = row.cells[cellIndex].textContent.replace(/[%\s,]/g, '');
      var val = Number.parseFloat(raw);
      return Number.isFinite(val) ? val : -1;
    };

    var getSortValue = function (row, key) {
      if (key === 'rank') return numFromCell(row, 0);
      if (key === 'streamer') return row.cells[1].textContent.trim().toLowerCase();
      if (key === 'count') return numFromCell(row, 2);
      if (key === 'ratio') return numFromCell(row, 3);
      if (key === 'active_rate') return numFromCell(row, 4);
      if (key === 'inactive_rate') return numFromCell(row, 5);
      return numFromCell(row, 0);
    };

    var sortOwnersTable = function (key, dir) {
      var rows = Array.from(ownersBody.rows);
      rows.sort(function (a, b) {
        var av = getSortValue(a, key);
        var bv = getSortValue(b, key);
        var cmp = 0;
        if (typeof av === 'string' && typeof bv === 'string') {
          cmp = av.localeCompare(bv, 'ja');
        } else {
          cmp = av - bv;
        }
        if (cmp === 0) {
          cmp = numFromCell(a, 0) - numFromCell(b, 0);
        }
        return dir === 'asc' ? cmp : -cmp;
      });
      rows.forEach(function (row) { ownersBody.appendChild(row); });
      ownerHeaders.forEach(function (header) {
        header.dataset.sortState = header.dataset.sortKey === key ? dir : '';
      });
    };

    ownerHeaders.forEach(function (header) {
      header.addEventListener('click', function () {
        var key = header.dataset.sortKey;
        var defaultDir = header.dataset.defaultDir || 'asc';
        var nextDir = defaultDir;
        if (currentSortKey === key) {
          nextDir = currentSortDir === 'asc' ? 'desc' : 'asc';
        }
        currentSortKey = key;
        currentSortDir = nextDir;
        sortOwnersTable(key, nextDir);
      });
    });

    currentSortKey = 'count';
    currentSortDir = 'desc';
    sortOwnersTable(currentSortKey, currentSortDir);
  }

  // ---- コメント影響度チャート ----
  var impactStatsEl = document.getElementById('impact-stats-data');
  if (impactStatsEl) {
    var impactData = JSON.parse(impactStatsEl.textContent);
    if (impactData && impactData.length > 0) {
      var impactLabels = impactData.map(function (d) { return d.owner_display_name; });
      var activeValues = impactData.map(function (d) { return d.avg_others_active; });
      var inactiveValues = impactData.map(function (d) { return d.avg_others_inactive; });

      var ctxImpact = document.getElementById('impactChart').getContext('2d');
      new Chart(ctxImpact, {
        type: 'bar',
        data: {
          labels: impactLabels,
          datasets: [
            {
              label: '活動時の平均他コメント数(/5分)',
              data: activeValues,
              backgroundColor: 'rgba(54, 162, 235, 0.5)',
              borderColor: 'rgba(54, 162, 235, 1)',
              borderWidth: 1
            },
            {
              label: '非活動時の平均他コメント数(/5分)',
              data: inactiveValues,
              backgroundColor: 'rgba(255, 99, 132, 0.5)',
              borderColor: 'rgba(255, 99, 132, 1)',
              borderWidth: 1
            }
          ]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          indexAxis: impactData.length > 5 ? 'y' : 'x',
          scales: {
            x: { beginAtZero: true, ticks: { color: textColor }, grid: { color: gridColor } },
            y: { ticks: { color: textColor }, grid: { color: gridColor } }
          },
          plugins: {
            legend: { labels: { color: textColor } },
            tooltip: {
              callbacks: {
                afterBody: function (context) {
                  var idx = context[0].dataIndex;
                  var item = impactData[idx];
                  var sig = item.p_value < 0.001 ? '***' : item.p_value < 0.01 ? '**' : item.p_value < 0.05 ? '*' : 'n.s.';
                  return 'コメント変化率: ' + item.comment_change + '% (' + sig + ', p=' + item.p_value + ')\n人数変化率: ' + item.unique_change + '% (p=' + item.p_value_unique + ')';
                }
              }
            }
          }
        }
      });
    }
  }
})();
