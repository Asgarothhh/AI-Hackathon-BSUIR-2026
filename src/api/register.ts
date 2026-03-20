export const register = async (email: string, password: string) => {
    const response = await fetch("http://127.0.0.1:8000/auth/register", {
        method: "post",
        headers: {
            "Content-type": "application/json"
        },
        body: JSON.stringify({ email, password })
    })

    console.log(response)
}