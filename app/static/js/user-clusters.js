(function () {
  const loginEl = document.getElementById('clusters-login-data');
  const platformEl = document.getElementById('clusters-platform-data');
  if (!loginEl || !platformEl) {return;}

  const PLATFORM = JSON.parse(platformEl.textContent);
  const SUBCLUSTER_URL = `${location.pathname  }/subcluster`;

  /**
   *
   * @param btn
   * @param nClusters
   */
  async function drillDown(btn, nClusters) {
    const centroid = JSON.parse(btn.dataset.centroid);
    const nMembers = parseInt(btn.dataset.size, 10);
    btn.disabled = true;
    btn.textContent = '分析中...';

    try {
      const resp = await fetch(SUBCLUSTER_URL, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({centroid, n_members: nMembers, n_clusters: nClusters}),
      });
      const data = await resp.json();
      if (data.error) {throw new Error(data.error);}

      const wrap = document.createElement('div');
      wrap.className = 'subclusters-wrap';

      for (let i = 0; i < data.subclusters.length; i++) {
        const sc = data.subclusters[i];
        const card = document.createElement('div');
        card.className = 'subcluster-card';

        const head = document.createElement('div');
        head.className = 'subcluster-head';
        head.innerHTML = `<span>#${  i + 1  }</span><span>${  sc.size  } 件</span>`;

        const ul = document.createElement('ul');
        ul.className = 'subcluster-examples';
        for (let j = 0; j < sc.representatives.length; j++) {
          const li = document.createElement('li');
          li.textContent = sc.representatives[j];
          ul.appendChild(li);
        }

        card.appendChild(head);
        card.appendChild(ul);

        if (sc.size >= 8) {
          const subBtn = document.createElement('button');
          subBtn.className = 'sub-drill-btn';
          subBtn.textContent = 'さらに分解 →';
          subBtn.dataset.centroid = JSON.stringify(sc.centroid);
          subBtn.dataset.size = String(sc.size);
          subBtn.onclick = function () { drillDown(this, 4); };
          card.appendChild(subBtn);
        }

        if (sc.size <= 200) {
          const viewForm = document.createElement('form');
          viewForm.method = 'POST';
          viewForm.action = location.pathname.replace('/clusters', '/cluster-comments');
          viewForm.target = '_blank';
          viewForm.style.marginTop = '4px';
          viewForm.innerHTML =
            `<input type="hidden" name="centroid" value="${  JSON.stringify(sc.centroid).replace(/"/g, '&quot;')  }">` +
            `<input type="hidden" name="n_members" value="${  sc.size  }">` +
            `<input type="hidden" name="platform" value="${  PLATFORM  }">` +
            `<button type="submit" class="view-btn">コメント一覧を見る (${  sc.size  } 件)</button>`;
          card.appendChild(viewForm);
        }

        wrap.appendChild(card);
      }

      btn.replaceWith(wrap);
    } catch (e) {
      btn.disabled = false;
      btn.textContent = `エラー: ${  e.message}`;
    }
  }

  // drillDown is referenced by onclick attributes in HTML
  window.drillDown = drillDown;
})();
