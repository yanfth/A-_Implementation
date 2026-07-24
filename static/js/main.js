const form = document.getElementById('routeForm');
        const idr = v => 'Rp ' + Number(v).toLocaleString('id-ID');

        function formatWaktu(totalJam) {
            const jamBulat = Math.floor(totalJam);
            const menit = Math.round((totalJam - jamBulat) * 60);
            const hari = Math.floor(jamBulat / 24);
            const sisaJam = jamBulat % 24;

            let bagianJam = `${sisaJam} Jam`;
            if (menit > 0) bagianJam += ` ${menit} Menit`;

            if (hari > 0) {
                return `${hari} Hari ${bagianJam}<br><span style="font-weight:500;color:var(--muted);font-size:11px;">(${totalJam} Jam total)</span>`;
            }
            return `${bagianJam}`;
        }

        function updateKartu(prefix, data) {
            document.getElementById(`${prefix}-jarak`).textContent = data.jarak + ' KM';
            document.getElementById(`${prefix}-waktu`).innerHTML = formatWaktu(data.waktu);
            document.getElementById(`${prefix}-bbm`).textContent = idr(data.bbm);
            document.getElementById(`${prefix}-tol`).textContent = idr(data.tol);
            document.getElementById(`${prefix}-total`).textContent = idr(data.biaya_total);
            document.getElementById(`${prefix}-path`).textContent = data.path;
        }

        function kirimDataForm() {
            document.getElementById('loadingOverlay').classList.add('show');

            const formData = new FormData(form);
            fetch('/hitung', { method: 'POST', body: formData })
                .then(r => r.json())
                .then(data => {
                    document.getElementById('loadingOverlay').classList.remove('show');
                    document.getElementById('hasilSection').classList.add('visible');

                    // Update kartu tol & arteri
                    updateKartu('tol', data.tol);
                    updateKartu('arteri', data.arteri);

                    // Tandai rekomendasi
                    document.getElementById('cardTol').classList.toggle('recommended', data.rekomendasi === 'tol');
                    document.getElementById('cardArteri').classList.toggle('recommended', data.rekomendasi === 'arteri');
                    document.getElementById('badgeTol').innerHTML = data.rekomendasi === 'tol' ? '<span class="badge-rekomendasi">✓ Rekomendasi</span>' : '';
                    document.getElementById('badgeArteri').innerHTML = data.rekomendasi === 'arteri' ? '<span class="badge-rekomendasi">✓ Rekomendasi</span>' : '';

                    // Update peta
                    document.getElementById('mapContainer').innerHTML = data.map_html;

                    // Update tabel algoritma
                    document.getElementById('algoTableBody').innerHTML = `
                <tr class="astar">
                    <td>
                        <div class="method-name">A* (Rekomendasi AI)</div>
                        <div class="method-ms">Komputasi: ${data.astar.waktu_komputasi} ms</div>
                    </td>
                    <td><div class="path-chip">${data.astar.path}</div></td>
                    <td>${data.astar.jarak} Km</td>
                    <td style="color:var(--shopee-orange);font-weight:700;">${formatWaktu(data.astar.waktu)}</td>
                    <td>${idr(data.astar.bbm)}</td>
                    <td>${idr(data.astar.tol)}</td>
                    <td><strong>${idr(data.astar.biaya_total)}</strong></td>
                </tr>
                <tr class="dijkstra">
                    <td>
                        <div class="method-name">Dijkstra (Baseline)</div>
                        <div class="method-ms">Komputasi: ${data.dijkstra.waktu_komputasi} ms</div>
                    </td>
                    <td><div class="path-chip">${data.dijkstra.path}</div></td>
                    <td>${data.dijkstra.jarak} Km</td>
                    <td>${formatWaktu(data.dijkstra.waktu)}</td>
                    <td>${idr(data.dijkstra.bbm)}</td>
                    <td>${idr(data.dijkstra.tol)}</td>
                    <td>${idr(data.dijkstra.biaya_total)}</td>
                </tr>
            `;
                })
                .catch(() => {
                    document.getElementById('loadingOverlay').classList.remove('show');
                });
        }

        window.addEventListener('DOMContentLoaded', kirimDataForm);
        form.addEventListener('submit', function (e) {
            e.preventDefault();
            kirimDataForm();
        });