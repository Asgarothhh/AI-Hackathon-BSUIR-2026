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

export async function exportFile(): Promise<void> {
    try {
        const response = await fetch(
            `http://localhost:8000/api/v1/comparisons/last/pdf`
        );

        if (!response.ok) {
            throw new Error(`Ошибка загрузки: ${response.status}`);
        }

        const blob = await response.blob();

        const url = window.URL.createObjectURL(blob);

        const a = document.createElement("a");
        a.href = url;
        a.download = "report.pdf"; 

        document.body.appendChild(a);
        a.click();

        a.remove();
        window.URL.revokeObjectURL(url);

    } catch (error) {
        console.error("Ошибка при загрузке файла:", error);
    }
}