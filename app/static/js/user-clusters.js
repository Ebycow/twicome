(function () {
  var loginEl = document.getElementById('clusters-login-data');
  var platformEl = document.getElementById('clusters-platform-data');
  if (!loginEl || !platformEl) return;

  var LOGIN = JSON.parse(loginEl.textContent);
  var PLATFORM = JSON.parse(platformEl.textContent);
  var SUBCLUSTER_URL = location.pathname + '/subcluster';

  async function drillDown(btn, nClusters) {
    var centroid = JSON.parse(btn.dataset.centroid);
    var nMembers = parseInt(btn.dataset.size, 10);
    btn.disabled = true;
    btn.textContent = '分析中...';

    try {
      var resp = await fetch(SUBCLUSTER_URL, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({centroid: centroid, n_members: nMembers, n_clusters: nClusters}),
      });
      var data = await resp.json();
      if (data.error) throw new Error(data.error);

      var wrap = document.createElement('div');
      wrap.className = 'subclusters-wrap';

      for (var i = 0; i < data.subclusters.length; i++) {
        var sc = data.subclusters[i];
        var card = document.createElement('div');
        card.className = 'subcluster-card';

        var head = document.createElement('div');
        head.className = 'subcluster-head';
        head.innerHTML = '<span>#' + (i + 1) + '</span><span>' + sc.size + ' 件</span>';

        var ul = document.createElement('ul');
        ul.className = 'subcluster-examples';
        for (var j = 0; j < sc.representatives.length; j++) {
          var li = document.createElement('li');
          li.textContent = sc.representatives[j];
          ul.appendChild(li);
        }

        card.appendChild(head);
        card.appendChild(ul);

        if (sc.size >= 8) {
          var subBtn = document.createElement('button');
          subBtn.className = 'sub-drill-btn';
          subBtn.textContent = 'さらに分解 →';
          subBtn.dataset.centroid = JSON.stringify(sc.centroid);
          subBtn.dataset.size = String(sc.size);
          subBtn.onclick = function () { drillDown(this, 4); };
          card.appendChild(subBtn);
        }

        if (sc.size <= 200) {
          var viewForm = document.createElement('form');
          viewForm.method = 'POST';
          viewForm.action = location.pathname.replace('/clusters', '/cluster-comments');
          viewForm.target = '_blank';
          viewForm.style.marginTop = '4px';
          viewForm.innerHTML =
            '<input type="hidden" name="centroid" value="' + JSON.stringify(sc.centroid).replace(/"/g, '&quot;') + '">' +
            '<input type="hidden" name="n_members" value="' + sc.size + '">' +
            '<input type="hidden" name="platform" value="' + PLATFORM + '">' +
            '<button type="submit" class="view-btn">コメント一覧を見る (' + sc.size + ' 件)</button>';
          card.appendChild(viewForm);
        }

        wrap.appendChild(card);
      }

      btn.replaceWith(wrap);
    } catch (e) {
      btn.disabled = false;
      btn.textContent = 'エラー: ' + e.message;
    }
  }

  // drillDown is referenced by onclick attributes in HTML
  window.drillDown = drillDown;
})();
