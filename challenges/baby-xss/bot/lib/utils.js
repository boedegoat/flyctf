const { chromium, firefox, webkit } = require('playwright')
const { CONFIG, browserArgs } = require('./config')

/** @type {import('playwright').Browser} */
let initBrowser = null

async function getContext() {
	/** @type {import('playwright').BrowserContext} */
	let context = null
	if (CONFIG.APPEXTENSIONS === '') {
		if (initBrowser === null) {
			initBrowser = await (CONFIG.APPBROWSER === 'firefox'
				? firefox.launch(browserArgs)
				: chromium.launch(browserArgs))
		}
		context = await initBrowser.newContext()
	} else {
		context = await (CONFIG.APPBROWSER === 'firefox'
			? firefox.launch({ browserArgs })
			: chromium.launch(browserArgs)
		).newContext()
	}
	return context
}

function sleep(ms) {
	return new Promise((resolve) => setTimeout(resolve, ms))
}

module.exports = {
	sleep,
	getContext,
}
