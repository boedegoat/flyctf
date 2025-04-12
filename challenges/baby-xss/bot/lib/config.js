const path = require('path')
const fs = require('fs')

const CONFIG = {
	APPNAME: process.env['APPNAME'] || 'Admin',
	APPURL: process.env['APPURL'] || 'http://172.17.0.1',
	APPURLREGEX: process.env['APPURLREGEX'] || '^.*$',
	APPFLAG: process.env['APPFLAG'] || 'dev{flag}',
	APPLIMITTIME: Number(process.env['APPLIMITTIME'] || '60000'),
	APPLIMIT: Number(process.env['APPLIMIT'] || '5'),
	APPEXTENSIONS: (() => {
		const extDir = path.join(__dirname, '../extensions')
		const dir = []
		fs.readdirSync(extDir).forEach((file) => {
			if (fs.lstatSync(path.join(extDir, file)).isDirectory()) {
				dir.push(path.join(extDir, file))
			}
		})
		return dir.join(',')
	})(),
	APPBROWSER: process.env['BROWSER'] || 'chromium',
}

const browserArgs = {
	headless: (() => {
		const is_x11_exists = fs.existsSync('/tmp/.X11-unix')
		if (process.env['DISPLAY'] !== undefined && is_x11_exists) {
			return false
		}
		return true
	})(),
	args: [
		'--disable-dev-shm-usage',
		'--disable-gpu',
		'--no-gpu',
		'--disable-default-apps',
		'--disable-translate',
		'--disable-device-discovery-notifications',
		'--disable-software-rasterizer',
		'--disable-xss-auditor',
		...(() => {
			if (CONFIG.APPEXTENSIONS === '') return []
			return [`--disable-extensions-except=${CONFIG.APPEXTENSIONS}`, `--load-extension=${CONFIG.APPEXTENSIONS}`]
		})(),
	],
	ignoreHTTPSErrors: true,
}

const WAIT_UNTIL = {
	NAVIGATION_BEGINS: 'commit',
	NO_NETWORK_CONNECTION: 'networkidle',
	WEBPAGE_FULLY_LOADED: 'load',
	INITIAL_HTML_LOADED: 'domcontentloaded',
}

module.exports = {
	CONFIG,
	browserArgs,
	WAIT_UNTIL,
}
