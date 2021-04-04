
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
        <template v-if="github_login">
          <cv-button v-on:click="signinGithub">
            Sign In Via Github
          </cv-button>
        </template>
        <template v-if="gitlab_login">
          <cv-button v-on:click="signinGitlab">
            Sign In Via Gitlab
          </cv-button>
        </template>
        <template v-if="google_login">
          <cv-button v-on:click="signinGoogle">
            Sign In Via Google
          </cv-button>
        </template>
        <cv-header-global-action aria-label="User avatar" aria-controls="user-panel">
        <UserAvatar20 />
      </cv-header-global-action>
      </template>
    </template>
    <cv-side-nav id="side-nav">
      <cv-side-nav-items>
        <cv-side-nav-link href="/channels">
          Channels
        </cv-side-nav-link>
        <cv-side-nav-link href="/users">
          Users
        </cv-side-nav-link>
        <cv-side-nav-link href="/api-keys">
          Api Keys
        </cv-side-nav-link>
        <cv-side-nav-link href="/jobs">
          Jobs
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
        name: '',
        avatar_url: undefined,
        github_login: false,
        gitlab_login: false,
        google_login: false,
      };
    },
    created() {
      this.me();
      this.check_github_login();
      this.check_gitlab_login();
      this.check_google_login();
    //  TODO: get enabled login routes
    },
    methods: {
      signinGithub() {
        window.location.href = "/auth/github/login";
        console.log("Signing in via github");
      },
      signinGitlab() {
        window.location.href = "/auth/gitlab/login";
        console.log("Signing in via gitlab");
      },
      signinGoogle() {
        window.location.href = "/auth/google/login";
        console.log("Signing in via google");
      },
      logout() {
        window.location.href = "/auth/logout";
        console.log("Signing out.")
      },
      me() {
        fetch("/api/me").then((msg) => {
          if (msg.status === 200) {
            msg.json().then((decoded) => {
              this.name = decoded.name || decoded.user.username;
              this.avatar_url = decoded.avatar_url;
            })
          } else if (msg.status === 401) {
            this.name = '';
            this.avatar_url = undefined;
          }
        })
      },
      check_github_login() {
        fetch("/auth/github/enabled").then((msg) => {
          this.github_login = msg.status === 200;
        }).catch((err) => {
          console.log(err);
          this.github_login = false;
        })
      },
      check_gitlab_login() {
        fetch("/auth/gitlab/enabled").then((msg) => {
          this.gitlab_login = msg.status === 200;
        }).catch((err) => {
          console.log(err);
          this.gitlab_login = false;
        })
      },
      check_google_login() {
        fetch("/auth/google/enabled").then((msg) => {
          this.google_login = msg.status === 200;
        }).catch((err) => {
          console.log(err);
          this.google_login = false;
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
