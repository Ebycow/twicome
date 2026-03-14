(function () {
  const loginEl = document.getElementById('clusters-login-data');
  const platformEl = document.getElementById('clusters-platform-data');
  const nEl = document.getElementById('clusters-n-data');
  if (!loginEl || !platformEl) {return;}

  const PLATFORM = JSON.parse(platformEl.textContent);
  const N_CLUSTERS_TOP = nEl ? parseInt(nEl.textContent, 10) : 8;
  const SUBCLUSTER_URL = `${location.pathname  }/subcluster`;
  const CLUSTER_COMMENTS_BASE = location.pathname.replace('/clusters', '/cluster-comments');

  /**
   * @param btn - ドリルダウンボタン要素
   * @param nClusters - サブクラスタ数
   * @param parentPath - 親までのパス文字列（例: "2" または "2,1"）
   */
  async function drillDown(btn, nClusters, parentPath) {
    const centroid = JSON.parse(btn.dataset.centroid);
    const nMembers = parseInt(btn.dataset.size, 10);
    const memberIndices = btn.dataset.memberIndices ? JSON.parse(btn.dataset.memberIndices) : null;
    btn.disabled = true;
    btn.textContent = '分析中...';

    try {
      const body = {centroid, n_members: nMembers, n_clusters: nClusters};
      if (memberIndices) {body.member_indices = memberIndices;}
      const resp = await fetch(SUBCLUSTER_URL, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body),
      });
      const data = await resp.json();
      if (data.error) {throw new Error(data.error);}

      const wrap = document.createElement('div');
      wrap.className = 'subclusters-wrap';

      for (let i = 0; i < data.subclusters.length; i++) {
        const sc = data.subclusters[i];
        const myPath = parentPath !== undefined && parentPath !== '' ? `${parentPath  },${  i}` : String(i);
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
          subBtn.dataset.path = myPath;
          if (sc.member_indices) {subBtn.dataset.memberIndices = JSON.stringify(sc.member_indices);}
          subBtn.onclick = function () { drillDown(this, 4, this.dataset.path); };
          card.appendChild(subBtn);
        }

        if (sc.size <= 200) {
          const platformParam = PLATFORM !== 'twitch' ? `&platform=${  encodeURIComponent(PLATFORM)}` : '';
          const viewLink = document.createElement('a');
          viewLink.href = `${CLUSTER_COMMENTS_BASE  }?n_clusters=${  N_CLUSTERS_TOP  }&path=${  myPath  }${  platformParam}`;
          viewLink.target = '_blank';
          viewLink.className = 'view-btn';
          viewLink.textContent = `コメント一覧を見る (${  sc.size  } 件)`;
          card.appendChild(viewLink);
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
