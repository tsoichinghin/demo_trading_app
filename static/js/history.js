document.addEventListener('DOMContentLoaded', function() {
    var pagination = document.querySelector('.pagination');
    var currentPage = parseInt(pagination.dataset.currentPage);
    var totalPages = parseInt(pagination.dataset.totalPages);
    var totalTrades = parseInt(pagination.dataset.totalTrades);

    // 生成分頁按鈕
    if (currentPage > 1) {
        pagination.innerHTML += `<button onclick="goToPage(${currentPage - 1})">上一頁</button>`;
    }
    for (var p = 1; p <= totalPages; p++) {
        if (p === currentPage) {
            pagination.innerHTML += `<button disabled>${p}</button>`;
        } else {
            pagination.innerHTML += `<button onclick="goToPage(${p})">${p}</button>`;
        }
    }
    if (currentPage < totalPages) {
        pagination.innerHTML += `<button onclick="goToPage(${currentPage + 1})">下一頁</button>`;
    }
    pagination.innerHTML += `<p>總交易數: ${totalTrades} | 當前頁: ${currentPage} / ${totalPages}</p>`;
});

function goToPage(page) {
    window.location.href = '/history/' + page;
}

function goToPositions() {
    window.location.href = '/';
}