package middleware

import (
	"net/http"
	"strings"

	"hakathon/security"

	"github.com/gin-gonic/gin"
)

func AuthRequired() gin.HandlerFunc {
	return func(c *gin.Context) {
		auth := c.GetHeader("Authorization")
		if auth == "" {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "Токен не предоставлен!"})
			return
		}

		token := strings.TrimPrefix(auth, "Bearer ")
		AcToken, err := security.ValidateToken(token)
		if err != nil {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "Неверный или просроченный токен!"})
			return
		}

		// Сохраняем данные ученика в контекст запроса
		c.Set("Role", AcToken.Role)
		c.Set("AuthID", AcToken.AuthID)

		c.Next()
	}
}
