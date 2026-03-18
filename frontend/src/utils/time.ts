export function isoToTurkishDateTime(isoDate: string) {
	const date = new Date(isoDate);

	return date.toLocaleString('tr-TR', {
		day: '2-digit',
		month: '2-digit',
		year: 'numeric',
		hour: '2-digit',
		minute: '2-digit',
		second: '2-digit'
	});
}

export function getDaysDifference(dateStr1: string, dateStr2: string) {
	const date1 = parseDateFlex(dateStr1)
	const date2 = parseDateFlex(dateStr2)

	if (isNaN(date1.getTime()) || isNaN(date2.getTime())) {
		return null
	}

	const diffMs = date1.getTime() - date2.getTime();

	const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24))

	return diffDays
}

export function parseDateFlex(strDate: string) {
	strDate = strDate?.trim()

	if (/^\d{2}\.\d{2}\.\d{4}$/.test(strDate)) {
		const [day, month, year] = strDate.split(".").map(Number)
		return new Date(year, month - 1, day)
	}

	if (/^\d{4}[-/]\d{2}[-/]\d{2}$/.test(strDate)) {
		return new Date(strDate)
	}

	const d = new Date(strDate)
	if (!isNaN(d.getTime())) return d

	throw new Error("Invalid Date Format: " + strDate)
}

export function getTodayEUFormat() {
	const today = new Date();
	const euFormat = new Intl.DateTimeFormat('tr-TR', {
		day: '2-digit',
		month: '2-digit',
		year: 'numeric'
	}).format(today);

	return euFormat
}

export function sortedDates(dates: any[]) {
	return dates.sort((a, b) => {
		const [ad, am, ay] = a.split('.').map(Number)
		const [bd, bm, by] = b.split('.').map(Number)
		return new Date(ay, am - 1, ad).getTime() - new Date(by, bm - 1, bd).getTime()
	})
}

export function findPreviousDate(datesArray: string[], targetDateStr: string) {
	const targetDate = parseDateFlex(targetDateStr);

	let closestIndex = -1;
	let minDiff = Infinity;

	datesArray.forEach((dateStr, index) => {
		const date = parseDateFlex(dateStr);

		let diff = date.getTime() - targetDate.getTime();
		if (diff < 0) {
			diff = Math.abs(diff)
			if (diff < minDiff) {
				minDiff = diff;
				closestIndex = index; // Orijinal stringi döndür
			}
		}
	});

	return closestIndex;
}