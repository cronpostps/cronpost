<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>In-App Messenger - CronPost</title>
    <link href="/css/bootstrap.min.css" rel="stylesheet">
    <link href="/css/style.css" rel="stylesheet">
    <style>
        {* Custom styles for the new IAM layout *}
        #iam-main-card .card-header {
            padding: 0.5rem 1rem;
        }
        #iam-nav-tabs .nav-link {
            padding: 0.75rem 1rem;
            cursor: pointer;
        }
        #iam-content-pane {
            min-height: 65vh;
            position: relative;
        }
        #iam-message-detail-view .message-body {
            white-space: pre-wrap;
            word-wrap: break-word;
            padding: 1.25rem;
            border-top: 1px solid var(--bs-border-color);
        }
    </style>
</head>
<body class="theme-dark">
    {* Header will be loaded by JS *}
    <div id="header-placeholder"></div>

    <div class="container mt-4">
        <div id="iam-main-card" class="card">
            {* Toolbar for navigation and main actions *}
            <div class="card-header d-flex justify-content-between align-items-center" id="iam-toolbar">
                <ul class="nav nav-pills" id="iam-nav-tabs">
                    <li class="nav-item">
                        <a class="nav-link active" data-folder="inbox">Inbox</a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link" data-folder="sent">Sent</a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link" data-folder="contacts">Contacts</a>
                    </li>
                </ul>
                <button class="btn btn-primary" id="iam-compose-btn">Compose</button>
            </div>

            {* Search Section *}
            <div class="p-3 border-bottom" id="iam-search-section">
                <div class="input-group">
                    <input type="search" id="iam-search-input" class="form-control" placeholder="Search by sender, subject, or content...">
                    <button id="iam-search-btn" class="btn btn-outline-secondary">Search</button>
                </div>
            </div>

            {* Main Content Pane where lists and messages will be loaded *}
            <div class="card-body" id="iam-content-pane">
                <div class="text-center p-5" id="iam-loading-spinner">
                    <div class="spinner-border" role="status">
                        <span class="visually-hidden">Loading...</span>
                    </div>
                </div>
            </div>
        </div>
    </div>

    {* Footer will be loaded by JS *}
    <div id="footer-placeholder"></div>

    {* Scripts *}
    <script src="/js/bootstrap.bundle.min.js"></script>
    <script src="/js/utils.js"></script>
    <script src="/js/auth.js"></script>
    <script src="/js/pin-modal.js"></script>
    <script src="/js/header.js"></script>
    <script src="/js/iam.js"></script>
    <script>
        document.addEventListener('DOMContentLoaded', function() {
            loadHeader('_header-dashboard.html');
            // We won't load the footer here as it may contain shared modals that conflict
        });
    </script>
</body>
</html>