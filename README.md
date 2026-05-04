### TVMS

Timetable and Venue management system that will manage Venue utilization and availability for any Emergency schedule in the Institute like Universities.

TVMS is a Frappe Desk/pages app. Its user interface is delivered through DocType forms, list views, and Frappe pages; there is no separate single-page app or custom client build pipeline.

Main Desk routes include `/app/timetable` for imported timetable records, `/app/tvms-timetable` for the static weekly timetable grid, `/app/venue` for venue management, and `/app/emergency-session` for emergency scheduling.

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench install-app tvms
```

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/tvms
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### CI

This app can use GitHub Actions for CI. The following workflows are configured:

- CI: Installs this app and runs unit tests on every push to `develop` branch.
- Linters: Runs [Frappe Semgrep Rules](https://github.com/frappe/semgrep-rules) and [pip-audit](https://pypi.org/project/pip-audit/) on every pull request.


### License

mit
