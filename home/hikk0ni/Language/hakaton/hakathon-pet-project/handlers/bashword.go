package handlers

import (
	"fmt"
	"log"
	"net/http"
	"strconv"
	"strings"

	"hakathon/models"
	"hakathon/repository"
	"hakathon/security"

	"github.com/gin-gonic/gin"
)

// --- 1. АВТОРИЗАЦИЯ И РЕГИСТРАЦИЯ ---

func Login(c *gin.Context) {
	var req models.RequestAuth
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Неверный формат запроса"})
		return
	}

	auth, err := repository.FindAuthByEmail(req.Email)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Пользователь не найден"})
		return
	}

	if err := security.CheckHashPassword(req.Password, auth.Password); err != nil {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Неверный пароль"})
		return
	}

	td, err := security.GenerateToken(auth.ID, auth.Role)
	if err != nil {
		log.Println("Ошибка генерации токена:", err)
		c.JSON(http.StatusOK, gin.H{"access_token": "demo_token", "email": req.Email})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"access_token": td.AccessToken,
		"email":        req.Email,
	})
}

func Register(c *gin.Context) {
	var req models.RequestRegister
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Неверные данные"})
		return
	}

	authID, err := repository.CreateUser(&req)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Email уже занят"})
		return
	}

	td, err := security.GenerateToken(authID, "student")
	if err != nil {
		c.JSON(http.StatusOK, gin.H{"access_token": "demo_token", "email": req.Email})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"access_token": td.AccessToken,
		"email":        req.Email,
	})
}

// --- 2. БАЗОВЫЕ ЗАДАНИЯ ---

func GetDailyTask(c *gin.Context) {
	task, err := repository.GetRandomTask()
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Нет заданий"})
		return
	}
	c.JSON(http.StatusOK, task)
}

func GetTaskByID(c *gin.Context) {
	idStr := c.Param("id")
	id, _ := strconv.Atoi(idStr)

	task, err := repository.GetTaskByID(uint(id))
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Слово не найдено"})
		return
	}
	c.JSON(http.StatusOK, task)
}

// --- 3. СИНХРОНИЗАЦИЯ ПРОГРЕССА (КРОССПЛАТФОРМА) ---

type SyncData struct {
	Email       string `json:"email"`
	Score       int    `json:"score"`
	LearnedIDs  string `json:"learned_ids"`
	MasteredIDs string `json:"mastered_ids"`
	MistakesIDs string `json:"mistakes_ids"`
}

// Скачиваем прогресс с сервера

func PullSync(c *gin.Context) {
	email := c.Query("email")

	auth, err := repository.FindAuthByEmail(email)
	if err != nil {
		c.JSON(http.StatusOK, gin.H{})
		return
	}
	user, _ := repository.GetUserByAuthID(auth.ID)

	c.JSON(http.StatusOK, gin.H{
		"score":        user.Score,
		"learned_ids":  user.LearnedIDs,
		"mastered_ids": user.MasteredIDs,
		"mistakes_ids": user.MistakesIDs,
	})
}

func PushSync(c *gin.Context) {
	var data struct {
		Email       string `json:"email"`
		Score       int    `json:"score"`
		LearnedIDs  string `json:"learned_ids"`
		MasteredIDs string `json:"mastered_ids"`
		MistakesIDs string `json:"mistakes_ids"`
	}

	if err := c.ShouldBindJSON(&data); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "bad request"})
		return
	}

	auth, err := repository.FindAuthByEmail(data.Email)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "user not found"})
		return
	}

	user, _ := repository.GetUserByAuthID(auth.ID)

	// Обновляем статистику пользователя
	user.Score = data.Score
	user.LearnedIDs = data.LearnedIDs
	user.MasteredIDs = data.MasteredIDs
	user.MistakesIDs = data.MistakesIDs

	repository.UpdateUserStats(user) // Сохраняем в базу!

	c.JSON(http.StatusOK, gin.H{"status": "success"})
}

// --- 4. ДАННЫЕ ДЛЯ ИНТЕРФЕЙСА ВЕБ-САЙТА ---

func GetProfile(c *gin.Context) {
	email := c.Query("email") // ИСПРАВЛЕНО: читаем из URL ?email=...

	auth, err := repository.FindAuthByEmail(email)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "not found"})
		return
	}
	user, _ := repository.GetUserByAuthID(auth.ID)

	lCount, mCount := 0, 0
	if user.LearnedIDs != "" {
		lCount = len(strings.Split(user.LearnedIDs, ","))
	}
	if user.MasteredIDs != "" {
		mCount = len(strings.Split(user.MasteredIDs, ","))
	}

	c.JSON(http.StatusOK, gin.H{
		"name": user.Name, "email": auth.Email, "score": user.Score,
		"learned": lCount, "mastered": mCount,
	})
}

// Получаем глобальный топ-10
func GetRating(c *gin.Context) {
	top, err := repository.GetTopUsers()
	if err != nil || top == nil {
		c.JSON(http.StatusOK, []interface{}{})
		return
	}
	c.JSON(http.StatusOK, top)
}

func GetDictionary(c *gin.Context) {
	email := c.Query("email") // ИСПРАВЛЕНО: читаем из URL ?email=...

	auth, err := repository.FindAuthByEmail(email)
	if err != nil {
		c.JSON(http.StatusOK, []interface{}{})
		return
	}
	user, _ := repository.GetUserByAuthID(auth.ID)

	var dict []map[string]string
	if user.LearnedIDs != "" {
		ids := strings.Split(user.LearnedIDs, ",")
		for _, idStr := range ids {
			if idStr == "" {
				continue
			}
			var id uint
			fmt.Sscanf(idStr, "%d", &id)
			if task, err := repository.GetTaskByID(id); err == nil {
				dict = append(dict, map[string]string{"ba": task.TextBa, "ru": task.Translation})
			}
		}
	}
	c.JSON(http.StatusOK, dict)
}
