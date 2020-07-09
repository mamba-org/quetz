
<template>
  <cv-header aria-label="Header">
    <cv-skip-to-content href="#main-content">
      Skip to content
    </cv-skip-to-content>
    <cv-header-name href="javascript:void(0)">
      Quetz
    </cv-header-name>
    <template slot="header-global">
      <template v-if="avatar_url">
        <div class="user_welcome">Welcome, <i>{{ name }}</i></div>
        <cv-button v-on:click="logout">Logout</cv-button>
        <img class="avatar-img" :src="avatar_url"  />
      </template>
      <template v-else>
        <cv-button v-on:click="signin">
          Sign In
        </cv-button>
      <cv-header-global-action aria-label="User avatar" aria-controls="user-panel">
        <!-- <img :src="avatar_url" v-if="avatar_url" /> -->

        <UserAvatar20 />
      </cv-header-global-action>
      </template>
    </template>
    <cv-side-nav id="side-nav">
      <cv-side-nav-items>
        <cv-side-nav-link href="/#/channels">
          Channels
        </cv-side-nav-link>
        <cv-side-nav-link href="/#/users">
          Users
        </cv-side-nav-link>
      </cv-side-nav-items>
    </cv-side-nav>
  </cv-header>

</template>

<script>
  import UserAvatar20 from '@carbon/icons-vue/es/user--avatar/20';

  export default {
    components: {
      UserAvatar20
    },
    name: 'Header',
    data() {
      return {
        yourName: '',
        visible: false,
        name: 'Dummy User',
        avatar_url: 'https://avatars0.githubusercontent.com/u/885054?v=4'
      };
    },
    created() {
      this.me();
    },
    methods: {
      signin() {
        window.location.href = "/auth/github/login";
        console.log("Signing in");
      },
      logout() {
        window.location.href = "/auth/logout";
        console.log("Signing out.")
      },
      me() {
        fetch("/api/me").then((msg) => {
          msg.json().then((decoded) => {
            this.name = decoded.name || decoded.user.username;
            this.avatar_url = decoded.avatar_url;
          })
        })
      },
      onClick() {
        this.visible = true;
      },
      modalClosed() {
        this.visible = false;
      },
    },
  };
</script>

<style>
  .user_welcome {
    padding: 17px;
  }
  .avatar-img {
    width: 48px;
    border-radius: 10px;
    padding: 5px;
  }
  .sample {
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    max-width: 600px;
    margin: 5% auto;
  }

  .cv-text-input {
    margin: 30px 0;
  }
</style>
