const { CONFIG, WAIT_UNTIL } = require('./lib/config')
const { sleep, getContext } = require('./lib/utils')

console.table(CONFIG)
console.log('Bot started...')

module.exports = {
	name: CONFIG.APPNAME,
	urlRegex: CONFIG.APPURLREGEX,
	rateLimit: {
		windowMs: CONFIG.APPLIMITTIME,
		limit: CONFIG.APPLIMIT,
	},
	bot: async (urlToVisit) => {
		const context = await getContext()
		try {
			const page = await context.newPage()
			await context.addCookies([
				{
					name: 'flag',
					httpOnly: false,
					value: CONFIG.APPFLAG,
					url: CONFIG.APPURL,
				},
			])

			console.log(`bot visiting ${urlToVisit}`)
			await page.goto(urlToVisit, {
				waitUntil: WAIT_UNTIL.NO_NETWORK_CONNECTION,
				timeout: 10 * 1000,
			})

			console.log('browser close...')
			return true
		} catch (e) {
			console.error(e)
			return false
		} finally {
			if (CONFIG.APPEXTENSIONS !== '') {
				await context.browser().close()
			} else {
				await context.close()
			}
		}
	},
}
