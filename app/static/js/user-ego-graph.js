/**
 * user-ego-graph.js
 * D3 force-directed ego graph for similar users on the stats page.
 * Requires D3 v7 to be loaded before this script.
 */
(function () {
  const loginEl = document.getElementById("user-data");
  const rootEl = document.getElementById("root-path-data");
  const container = document.getElementById("ego-graph-container");
  if (!loginEl || !rootEl || !container) { return; }

  const login = JSON.parse(loginEl.textContent);
  const rootPath = JSON.parse(rootEl.textContent);

  const loadingEl = container.querySelector(".ego-graph-loading");

  fetch(`${rootPath}/api/u/${encodeURIComponent(login)}/similar-users`)
    .then((r) => r.json())
    .then(({ nodes, edges }) => {
      if (loadingEl) { loadingEl.remove(); }
      if (nodes.length <= 1) {
        const msg = document.createElement("p");
        msg.className = "meta";
        msg.textContent = "共通の配信者が2件以上のユーザーが見つかりませんでした。";
        container.appendChild(msg);
        return;
      }
      renderGraph(container, nodes, edges, rootPath);
    })
    .catch(() => {
      if (loadingEl) { loadingEl.textContent = "グラフの読み込みに失敗しました。"; }
    });

  /**
   * D3 force graph をコンテナに描画する
   * @param {HTMLElement} graphContainer - グラフを挿入するコンテナ要素
   * @param {Array<object>} nodes - ノードデータ配列
   * @param {Array<object>} edges - エッジデータ配列
   * @param {string} root - アプリのルートパス
   */
  function renderGraph(graphContainer, nodes, edges, root) {
    const R_CENTER = 32;
    const R_NODE = 20;
    const width = Math.max(graphContainer.clientWidth || 700, 400);
    const height = 500;

    // Fix center node at canvas center
    const centerNode = nodes.find((n) => n.is_center);
    if (centerNode) {
      centerNode.fx = width / 2;
      centerNode.fy = height / 2;
    }

    const svg = d3
      .select(graphContainer)
      .append("svg")
      .attr("viewBox", `0 0 ${width} ${height}`)
      .attr("width", "100%")
      .style("display", "block")
      .style("overflow", "visible");

    const defs = svg.append("defs");

    // Circular clip paths for avatars
    nodes.forEach((node, i) => {
      const r = node.is_center ? R_CENTER : R_NODE;
      defs
        .append("clipPath")
        .attr("id", `ego-clip-${i}`)
        .append("circle")
        .attr("r", r);
      node._clipIdx = i;
    });

    // Force simulation
    const simulation = d3
      .forceSimulation(nodes)
      .force(
        "link",
        d3
          .forceLink(edges)
          .id((d) => d.id)
          .distance(150)
          .strength(0.7)
      )
      .force("charge", d3.forceManyBody().strength(-220))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force(
        "collide",
        d3.forceCollide((d) => (d.is_center ? R_CENTER + 14 : R_NODE + 20))
      );

    // Edge lines
    const link = svg
      .append("g")
      .attr("class", "ego-links")
      .selectAll("line")
      .data(edges)
      .join("line")
      .attr("stroke", "var(--accent)")
      .attr("stroke-opacity", 0.3)
      .attr("stroke-width", (d) => Math.min(1 + d.weight * 0.4, 6));

    // Node groups
    const nodeG = svg
      .append("g")
      .attr("class", "ego-nodes")
      .selectAll("g")
      .data(nodes)
      .join("g")
      .attr("class", "ego-node")
      .call(
        d3
          .drag()
          .on("start", (event, d) => {
            if (!event.active) { simulation.alphaTarget(0.3).restart(); }
            d.fx = d.x;
            d.fy = d.y;
          })
          .on("drag", (event, d) => {
            d.fx = event.x;
            d.fy = event.y;
          })
          .on("end", (event, d) => {
            if (!event.active) { simulation.alphaTarget(0); }
            // Release non-center nodes
            if (!d.is_center) {
              d.fx = null;
              d.fy = null;
            }
          })
      );

    // Background circle (border ring)
    nodeG
      .append("circle")
      .attr("r", (d) => (d.is_center ? R_CENTER + 3 : R_NODE + 3))
      .attr("fill", "var(--card-bg)")
      .attr("stroke", (d) => (d.is_center ? "var(--accent)" : "var(--card-border)"))
      .attr("stroke-width", (d) => (d.is_center ? 2.5 : 1.5));

    // Avatar image
    nodeG
      .append("image")
      .attr("href", (d) => d.profile_image_url || "")
      .attr("x", (d) => -(d.is_center ? R_CENTER : R_NODE))
      .attr("y", (d) => -(d.is_center ? R_CENTER : R_NODE))
      .attr("width", (d) => (d.is_center ? R_CENTER : R_NODE) * 2)
      .attr("height", (d) => (d.is_center ? R_CENTER : R_NODE) * 2)
      .attr("clip-path", (d) => `url(#ego-clip-${d._clipIdx})`);

    // Display name label below node
    nodeG
      .append("text")
      .text((d) => {
        const name = d.display_name || d.login;
        return name.length > 12 ? `${name.slice(0, 11)}…` : name;
      })
      .attr("text-anchor", "middle")
      .attr("y", (d) => (d.is_center ? R_CENTER : R_NODE) + 18)
      .attr("font-size", (d) => (d.is_center ? "13px" : "11px"))
      .attr("font-weight", (d) => (d.is_center ? "bold" : "normal"))
      .attr("fill", "var(--text-color)");

    // Shared count badge (top-right of non-center nodes)
    const badge = nodeG.filter((d) => !d.is_center);
    badge
      .append("circle")
      .attr("cx", R_NODE - 2)
      .attr("cy", -(R_NODE - 2))
      .attr("r", 9)
      .attr("fill", "var(--accent)");
    badge
      .append("text")
      .text((d) => d.shared_count)
      .attr("x", R_NODE - 2)
      .attr("y", -(R_NODE - 2) + 4)
      .attr("text-anchor", "middle")
      .attr("font-size", "9px")
      .attr("font-weight", "bold")
      .attr("fill", "#fff");

    // Click navigation for non-center nodes
    nodeG
      .filter((d) => !d.is_center)
      .style("cursor", "pointer")
      .on("click", (event, d) => {
        window.location.href = `${root}/u/${encodeURIComponent(d.login)}/stats`;
      });

    // Tooltip
    const tooltip = d3
      .select(graphContainer)
      .append("div")
      .attr("class", "ego-tooltip");

    nodeG
      .filter((d) => !d.is_center)
      .on("mouseenter", (event, d) => {
        const edge = edges.find((e) => {
          const tId = typeof e.target === "object" ? e.target.id : e.target;
          return tId === d.id;
        });
        if (!edge) { return; }
        const name = d.display_name || d.login;
        const streamers = edge.shared_streamers || [];
        tooltip
          .style("opacity", "1")
          .html(
            `<strong>${name}</strong><br><span class="ego-tooltip-label">共通の配信者 (${streamers.length}件):</span><br>${streamers.map((s) => `<span class="ego-tooltip-tag">${s}</span>`).join(" ")}`
          );
      })
      .on("mousemove", (event) => {
        const rect = graphContainer.getBoundingClientRect();
        const x = event.clientX - rect.left + 14;
        const y = event.clientY - rect.top - 10;
        tooltip.style("left", `${x}px`).style("top", `${y}px`);
      })
      .on("mouseleave", () => {
        tooltip.style("opacity", "0");
      });

    // Simulation tick: update positions
    simulation.on("tick", () => {
      const pad = 50;
      link
        .attr("x1", (d) => d.source.x)
        .attr("y1", (d) => d.source.y)
        .attr("x2", (d) => d.target.x)
        .attr("y2", (d) => d.target.y);
      nodeG.attr("transform", (d) => {
        const x = Math.max(pad, Math.min(width - pad, d.x));
        const y = Math.max(pad, Math.min(height - pad, d.y));
        return `translate(${x},${y})`;
      });
    });
  }
})();
