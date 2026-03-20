export async function uploadFiles(oldFile: File, newFile: File): Promise<void> {
    try {
        const formData = new FormData();
        formData.append("old_file", oldFile);
        formData.append("new_file", newFile);

        const response = await fetch(`http://localhost:8000/rag/compare/upload`, {
            method: "POST",
            body: formData,
            headers: {},
        });

        if (!response.ok) {
            throw new Error(`Ошибка загрузки: ${response.status}`);
        }

        const data = await response.json();
        console.log("Файл успешно загружен:", data);

        return data
    } catch (error) {
        console.error("Ошибка при загрузке файла:", error);
    }
}

