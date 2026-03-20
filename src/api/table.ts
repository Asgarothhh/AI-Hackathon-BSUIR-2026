export const fetchTableData = async (searchValue: string) => {
    const res = await fetch(`http://localhost:8000/api/v1/comparisons/track?page=1&per_page=50&q=${searchValue}`, {
        headers: {
            "Content-Type": "application/json"
        }
    })
    const data = await res.json()

    return data
}