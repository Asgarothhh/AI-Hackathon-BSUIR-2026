export const login = async (email: string, password: string) => {
    const response = await fetch("http://127.0.0.1:8000/auth/login", {
        method: "post",
        headers: {
            "Content-type": "application/json"
        },
        body: JSON.stringify({ email, password })
    })

    console.log(response)
}